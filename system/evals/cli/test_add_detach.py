"""Durable evals: `add` returns before its wiki filings finish (SPEC-cli-011).

Boundary: the `tapedeck` executable, every seam faked exactly as
test_add_autofile.py fakes them. The detachment is observed from outside, the
only place it exists: `add`'s pipes close and its process exits while a
maintainer is deliberately held open by a release file, and the filing lands
afterwards — proof the worker survived the `add` that spawned it and holds
none of the streams `add` was given. A worker that inherited stderr would keep
this suite's pipe open until the filing ended, which is exactly the today this
round removes.
"""

import os
import shlex
import subprocess
import sys
import time

import pytest
from conftest import REPO, TIMEOUT, run_cli
from test_add_autofile import FILE_BODY, VIDEO_A, configure_wiki, library_artifacts_intact
from test_add_collection import IDS, PLAYLIST, set_collection_pipeline

# The task arrives on stdin and is drained first (the seam's contract); then the
# maintainer marks itself started and holds until released, then files honestly.
HOLDS_THEN_FILES = (
    """#!/bin/sh
cat > /dev/null
touch "$TAPEDECK_HOME/filing-started"
until [ -e "$TAPEDECK_HOME/release" ]; do sleep 0.2; done
"""
    + FILE_BODY
)

# Leaves a marker in the home before refusing, so a test can know the worker
# reached this filing at all — a rejected run writes nothing durable anywhere
# else, by the wiki's own design (no commit, no chronology entry).
ALWAYS_FAILS_LEAVING_A_TRACE = """#!/bin/sh
cat > /dev/null
touch "$TAPEDECK_HOME/attempted-$TAPEDECK_VIDEO_ID"
echo "the fixture maintainer refuses to file $TAPEDECK_VIDEO_ID" >&2
exit 3
"""

GOOD = "#!/bin/sh\ncat > /dev/null\n" + FILE_BODY


def popen_cli(args, home):
    """run_cli's twin as a Popen, so a test can see *when* the pipes close
    rather than only what came through them."""
    cmd = os.environ.get("TAPEDECK_BIN", f"{sys.executable} -m cli")
    return subprocess.Popen(
        [*shlex.split(cmd), *args],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "TAPEDECK_HOME": str(home),
            "PYTHONPATH": os.pathsep.join(
                [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        },
    )


def settle(condition, message):
    """Poll until `condition()` holds — the eval's patience with a worker that
    is, by specification, nobody's child to wait on."""
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, message
        time.sleep(0.2)


def wiki_log(home):
    log = home / "wiki" / "log.md"
    return log.read_text() if log.is_file() else ""


def test_add_returns_while_the_filing_is_still_running(home):
    """The clause itself: a maintainer is holding the wiki open, and `add` is
    already gone — exit code returned, pipes closed, hand-off announced. The
    filing then lands on its own once the maintainer is released."""
    set_collection_pipeline(home)
    configure_wiki(home, auto=True, maintainer=HOLDS_THEN_FILES)
    proc = popen_cli(["add", VIDEO_A], home)
    try:
        out, err = proc.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        (home / "release").touch()
        proc.kill()
        proc.communicate()
        pytest.fail(
            "add held its pipes until the filing finished — the epilogue is "
            "not detached"
        )

    assert proc.returncode == 0, err
    assert library_artifacts_intact(home, VIDEO_A)
    page = home / "wiki" / "sources" / f"{VIDEO_A}.md"
    assert not page.exists(), (
        "the maintainer is still held open, so nothing can be filed yet — a "
        "page here means add waited for a filing it claims to have handed off"
    )
    assert "log" in err.lower(), (
        f"the hand-off names where outcomes land — the wiki's log:\n{err!r}"
    )

    (home / "release").touch()
    settle(page.is_file, "the handed-off filing never landed after release")


def test_a_sweep_hands_off_every_video_and_the_log_keeps_sweep_order(home):
    """Detachment must not cost SPEC-cli-009's accumulation: one worker files
    the sweep's videos in the order the sweep completed them, and the wiki's
    own chronology is the witness."""
    set_collection_pipeline(home)
    configure_wiki(home, auto=True, maintainer=GOOD)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    assert "log" in r.stderr.lower(), (
        f"one hand-off line per invocation, naming the wiki's log:\n{r.stderr!r}"
    )

    pages = [home / "wiki" / "sources" / f"{vid}.md" for vid in IDS]
    settle(
        lambda: all(p.is_file() for p in pages),
        f"not every filing landed: {[p.name for p in pages if not p.is_file()]}",
    )
    chronology = wiki_log(home)
    positions = [chronology.index(f"file | {vid}") for vid in IDS]
    assert positions == sorted(positions), (
        f"the worker files in sweep order, and the log shows it:\n{chronology}"
    )


def test_a_failure_after_hand_off_leaves_an_unfiled_video_not_a_stderr_note(home):
    """add's terminal has moved on by the time this filing fails, so no failure
    can appear on add's own stderr — the durable trace is the one a failed
    filing always leaves, an unfiled video that `wiki sync --dry-run` names."""
    set_collection_pipeline(home)
    configure_wiki(home, auto=True, maintainer=ALWAYS_FAILS_LEAVING_A_TRACE)
    r = run_cli(["add", VIDEO_A], home)
    assert r.returncode == 0, r.stderr
    assert library_artifacts_intact(home, VIDEO_A)
    assert "fail" not in r.stderr.lower(), (
        f"a failure after hand-off cannot appear on a stream add already "
        f"closed:\n{r.stderr!r}"
    )

    settle(
        lambda: (home / f"attempted-{VIDEO_A}").exists(),
        "the worker never reached the failing filing",
    )
    assert not (home / "wiki" / "sources" / f"{VIDEO_A}.md").exists(), (
        "a rejected filing must not leave the video looking filed"
    )
    dry = run_cli(["wiki", "sync", "--dry-run"], home)
    assert dry.returncode == 0, dry.stderr
    assert VIDEO_A in dry.stdout, (
        f"the discovery verb must name the video the failure left unfiled:\n"
        f"{dry.stdout!r}"
    )
