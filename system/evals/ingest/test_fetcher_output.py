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

import re

from conftest import run_component, set_fetcher

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
