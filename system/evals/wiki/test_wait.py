"""Durable evals: a filing may wait for the wiki instead of being refused
(SPEC-wiki-012).

Boundary: `python -m wiki` driven twice at once, exactly as test_lock.py drives
it — a first filing held open by a maintainer that waits for a release file, a
second arriving with `--wait`. The default remains test_lock.py's business and
stays pinned there: no flag, refuse at once. What this suite pins is the flag —
a waiting filing blocks instead of refusing, announces on stderr that it is
waiting, and once the holder finishes it lands as any filing lands: gate,
commit, log entry. On a free wiki the flag is invisible.
"""

import os
import shlex
import subprocess
import sys
import time

import wikilib
from conftest import REPO, TIMEOUT, add_video, set_maintainer, write_archive_page
from wikilib import NEXT, filed, subjects

# A third video, so the waiter has a filing of its own to do rather than
# arriving at an already-filed id and passing by way of the idempotent skip.
THIRD_META = {
    "id": "thirdvideo1",
    "title": "The Third Broadcast",
    "channel": "Fixture Channel",
    "upload_date": "2024-01-01",
    "duration_s": 600,
    "url": "https://www.youtube.com/watch?v=thirdvideo1",
}
THIRD = THIRD_META["id"]

# First invocation: hold the wiki until released, then file honestly. Every
# later invocation files at once — the waiter's filing must land, not stall on
# a second hold (contrast test_lock.py, whose second invocation files nothing
# because that suite's subject is the refusal, not the landing).
HOLDS_THEN_GOOD = f"""#!/bin/sh
if [ ! -e "$TAPEDECK_HOME/first-running" ]; then
  touch "$TAPEDECK_HOME/first-running"
  until [ -e "$TAPEDECK_HOME/release" ]; do sleep 0.2; done
fi
{wikilib.GOOD}
"""


def _spawn(home, *argv):
    """`python -m wiki <argv>` as a concurrent process, the way test_lock.py
    spawns its holder — installation-independent, capturing both streams."""
    cmd = [
        *shlex.split(os.environ.get("TAPEDECK_WIKI_CMD", f"{sys.executable} -m wiki")),
        *argv,
    ]
    return subprocess.Popen(
        cmd,
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


def _held_open(home):
    """Start `wiki file NEXT` and wait until its maintainer holds the wiki."""
    proc = _spawn(home, "file", NEXT)
    deadline = time.monotonic() + TIMEOUT
    while not (home / "first-running").exists():
        assert proc.poll() is None, proc.communicate()[1]
        assert time.monotonic() < deadline, "the holding maintainer never started"
        time.sleep(0.1)
    return proc


def test_a_wait_filing_blocks_through_a_held_wiki_and_then_lands(home, monkeypatch):
    """The stranding of a busy wiki, ended: the second filing arrives with
    --wait while the first holds the lock. It must not refuse, must still be
    alive while the holder works, must say it is waiting, and must file its own
    video once the wiki frees — two filings, two commits, nothing dropped."""
    wiki = filed(home, monkeypatch)
    add_video(home, THIRD_META, [{"start": 0.0, "end": 4.0, "text": "Third."}])
    write_archive_page(home, THIRD_META, wikilib.CH_SECTIONS)
    set_maintainer(home, HOLDS_THEN_GOOD)

    holder = _held_open(home)
    waiter = _spawn(home, "file", "--wait", THIRD)
    try:
        time.sleep(1.0)
        assert waiter.poll() is None, (
            "a --wait filing must block while the wiki is held, not exit: "
            f"{waiter.communicate()}"
        )
    finally:
        (home / "release").touch()
        h_out, h_err = holder.communicate(timeout=TIMEOUT)
        w_out, w_err = waiter.communicate(timeout=TIMEOUT)

    assert holder.returncode == 0, f"the held filing must land once released:\n{h_err}"
    assert waiter.returncode == 0, (
        f"the waiter must land after the holder, not refuse:\n{w_out}\n{w_err}"
    )
    assert "waiting" in w_err.lower(), (
        f"the wait announces itself on stderr before going silent:\n{w_err!r}"
    )
    assert (home / "wiki" / "sources" / f"{NEXT}.md").is_file()
    assert (home / "wiki" / "sources" / f"{THIRD}.md").is_file()
    assert subjects(wiki)[0] == f"wiki file {THIRD}", (
        f"the waited filing commits after the holder's: {subjects(wiki)}"
    )


def test_wait_on_a_free_wiki_is_invisible(home, monkeypatch):
    """--wait against a wiki nobody holds behaves as if the flag were absent:
    no waiting announcement, an ordinary accepted filing."""
    filed(home, monkeypatch)
    r = wikilib.run_component("wiki", ["file", "--wait", NEXT], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "waiting" not in r.stderr.lower(), (
        f"nothing was waited for, so nothing announces a wait:\n{r.stderr!r}"
    )
    assert (home / "wiki" / "sources" / f"{NEXT}.md").is_file()
