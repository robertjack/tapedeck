"""Durable evals: the fetcher's chatter is captured, not streamed
(SPEC-ingest-004).

Boundary: `python -m ingest add`, fetcher faked through config.toml exactly as
test_ingest.py fakes it. The fixture fetchers here are deliberately loud — a
marker line no real tool would print — so presence or absence of that marker in
`add`'s stderr is the capture behavior itself, observed from outside: absent on
a quiet success, present with --verbose, and replayed in full when the fetch
fails, because the tool's own words are the diagnosis (LESSON-0006's 403 was
diagnosable only from them).
"""

import os
import pty
import re
import shlex
import subprocess
import sys
import time

from conftest import REPO, TIMEOUT, run_component, set_fetcher

NOISE = "YTDLP-NOISE-MARKER-8842"

# test_ingest.py's honest fetcher, made loud.
CHATTY_OK = f"""#!/bin/sh
echo "{NOISE} extracting" >&2
echo "{NOISE} downloading" >&2
printf 'fake video bytes' > "$TAPEDECK_DEST/video.mp4"
cat > "$TAPEDECK_DEST/info.json" <<'JSON'
{{"id": "dQw4w9WgXcQ", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
 "description": "A fixture."}}
JSON
"""

CHATTY_FAILS = f"""#!/bin/sh
echo "{NOISE} extracting" >&2
echo "{NOISE} ERROR: unable to download video data" >&2
exit 1
"""

# Writes the video in two installments with a pause between them, so a
# heartbeat that watches the staging directory has something to see twice.
SLOW_OK = """#!/bin/sh
dd if=/dev/zero of="$TAPEDECK_DEST/video.mp4" bs=1024 count=200 2>/dev/null
sleep 3
dd if=/dev/zero of="$TAPEDECK_DEST/video.mp4" bs=1024 count=400 2>/dev/null
cat > "$TAPEDECK_DEST/info.json" <<'JSON'
{"id": "dQw4w9WgXcQ", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
 "description": "A fixture."}
JSON
"""

# Writes a sized info json FIRST — the shape yt-dlp stages before the video
# data moves — then lands MORE bytes than it declared (600 KB against a
# declared 400000), the way merging streams transiently overshoot. So one
# fixture exercises the denominator, the 99 cap, and the cadence at once.
SIZED_SLOW = """#!/bin/sh
cat > "$TAPEDECK_DEST/info.json" <<'JSON'
{"id": "dQw4w9WgXcQ", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
 "description": "A fixture.",
 "requested_formats": [{"filesize": 300000}, {"filesize_approx": 100000}]}
JSON
dd if=/dev/zero of="$TAPEDECK_DEST/video.mp4" bs=1024 count=200 2>/dev/null
sleep 4
dd if=/dev/zero of="$TAPEDECK_DEST/video.mp4" bs=1024 count=600 2>/dev/null
sleep 4
"""

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def add(home, *args):
    return run_component("ingest", ["add", *args], home)


def test_a_clean_fetch_swallows_the_tools_chatter(home):
    set_fetcher(home, CHATTY_OK)
    r = add(home, URL)
    assert r.returncode == 0, r.stderr
    assert (home / "library" / "dQw4w9WgXcQ" / "video.mp4").is_file()
    assert NOISE not in r.stderr, (
        f"the tool's chatter must be captured, not streamed:\n{r.stderr!r}"
    )
    assert NOISE not in r.stdout


def test_verbose_streams_the_tool_raw(home):
    set_fetcher(home, CHATTY_OK)
    r = add(home, URL, "--verbose")
    assert r.returncode == 0, r.stderr
    assert NOISE in r.stderr, (
        f"--verbose is the user asking to watch the tool itself:\n{r.stderr!r}"
    )


def test_a_failed_fetch_replays_everything_the_tool_said(home):
    set_fetcher(home, CHATTY_FAILS)
    r = add(home, URL)
    assert r.returncode == 1
    assert "ERROR: unable to download video data" in r.stderr, (
        f"the tool's own words are the diagnosis and must be replayed:\n{r.stderr!r}"
    )
    assert "fetcher" in r.stderr.lower(), "the existing failure line still closes it"
    assert not (home / "library" / "dQw4w9WgXcQ").exists()


def test_a_declared_size_turns_progress_into_a_capped_percentage(home):
    """The staged metadata names 400000 bytes; the fixture lands 600 KB. So a
    percent must appear (denominator read from the staging files, never the
    tool's stream), no percent may ever exceed 99 — only a clean exit says
    done — and an ~8-second fetch at the pinned every-three-seconds-or-so
    cadence is a handful of lines, not a firehose."""
    set_fetcher(home, SIZED_SLOW)
    r = add(home, URL)
    assert r.returncode == 0, r.stderr
    percents = [
        int(m.group(1))
        for line in r.stderr.splitlines()
        for m in [re.search(r"\((\d+)%\)", line)]
        if m
    ]
    assert percents, (
        f"a declared size must surface as a percentage:\n{r.stderr!r}"
    )
    assert all(p <= 99 for p in percents), (
        f"the estimate is approximate: cap at 99, only the exit says done: {percents}"
    )
    heartbeats = [
        line for line in r.stderr.splitlines() if "fetching" in line and "%" in line
    ]
    assert len(heartbeats) <= 4, (
        f"~8s of fetch at every-three-seconds-or-so is a handful of lines:\n"
        f"{heartbeats!r}"
    )


def test_no_declared_size_keeps_the_plain_byte_line(home):
    """SLOW_OK writes its info json last and names no sizes: the report
    degrades to bytes-so-far, never an invented denominator."""
    set_fetcher(home, SLOW_OK)
    r = add(home, URL)
    assert r.returncode == 0, r.stderr
    assert "%)" not in r.stderr, (
        f"no declared size, no percentage:\n{r.stderr!r}"
    )


def _add_on_a_tty(home, *args):
    """`python -m ingest add` with stderr on a pseudo-terminal, so the
    component sees what a person's terminal is: a TTY. Returns (exit code,
    everything written to that terminal, decoded)."""
    cmd = os.environ.get("TAPEDECK_INGEST_CMD", f"{sys.executable} -m ingest")
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [*shlex.split(cmd), "add", *args],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=slave,
        env={
            **os.environ,
            "TAPEDECK_HOME": str(home),
            "PYTHONPATH": os.pathsep.join(
                [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        },
    )
    os.close(slave)
    chunks, deadline = [], time.monotonic() + TIMEOUT
    while True:
        assert time.monotonic() < deadline, "the TTY fetch never finished"
        try:
            chunk = os.read(master, 4096)
        except OSError:  # EOF on macOS pty
            break
        if not chunk:
            break
        chunks.append(chunk)
    os.close(master)
    code = proc.wait(timeout=TIMEOUT)
    return code, b"".join(chunks).decode(errors="replace")


def test_a_tty_gets_one_redrawn_bar_not_a_stack_of_lines(home):
    """A person watching gets animation: the periodic reports redraw one line
    in place (bare carriage returns — a pty turns every real newline into
    CRLF, so a \\r NOT followed by \\n is the redraw itself) and the percent
    still appears. A program reading a pipe keeps the line-per-report form,
    which the capture-based tests above already pin."""
    set_fetcher(home, SIZED_SLOW)
    code, seen = _add_on_a_tty(home, URL)
    assert code == 0, seen
    redraws = len(re.findall(r"\r(?!\n)", seen))
    assert redraws >= 2, (
        f"a TTY report redraws one line in place rather than stacking:\n{seen!r}"
    )
    assert re.search(r"\(\d+%\)", seen), f"the bar still carries the percent:\n{seen!r}"
    stacked = [
        line for line in seen.replace("\r\n", "\n").split("\n")
        if "fetching" in line and "\r" not in line
    ]
    assert len(stacked) <= 2, (
        f"the redrawn line must not also stack as scrollback:\n{stacked!r}"
    )


def test_progress_is_reported_from_the_staging_bytes(home):
    """A fetch that takes seconds shows the bytes landing — derived from the
    staging directory, so it works for any tool behind the seam. The pin is
    loose on wording and cadence, firm on existence and origin: at least one
    report with a byte figure appears for a multi-second download."""
    set_fetcher(home, SLOW_OK)
    r = add(home, URL)
    assert r.returncode == 0, r.stderr
    sized = [
        line
        for line in r.stderr.splitlines()
        if re.search(r"\d+(\.\d+)?\s*(B|KB|KiB|MB|MiB)\b", line)
    ]
    assert sized, (
        f"a multi-second fetch must report bytes landed at least once:\n{r.stderr!r}"
    )
