"""Durable evals: one wiki operation at a time (SPEC-wiki-002, LESSON-0004).

Boundary: `python -m wiki` driven twice at once — the first operation held open by
a maintainer that waits for a release file, the second arriving while it holds the
wiki. The second must refuse fast, saying another wiki operation is running; the
read-only verbs must never be the ones refused. The lock's mechanics (advisory, in
the git directory, released with the process) are the spec's business — these
evals pin only what a caller can observe: refusal, its message, and that the held
operation still lands cleanly once released.
"""

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import wikilib
from conftest import REPO, TIMEOUT, set_maintainer
from wikilib import NEXT, filed, subjects, wiki_file, wiki_sync

# The first operation's maintainer: announce, then hold the wiki until released.
# A SECOND run of the same script (today's unlocked world reaches the seam twice)
# exits at once having written nothing, so no eval can deadlock on two waiters —
# and the silent exit files nothing, which today's gate rejects on its own terms,
# never with the refusal message these evals anchor on.
HOLDS_UNTIL_RELEASED = f"""#!/bin/sh
if [ -e "$TAPEDECK_HOME/first-running" ]; then
  exit 0
fi
touch "$TAPEDECK_HOME/first-running"
until [ -e "$TAPEDECK_HOME/release" ]; do sleep 0.2; done
{wikilib.GOOD}
"""

REFUSAL = "another wiki operation"


def _held_open(home):
    """Start `wiki file NEXT` as a concurrent process and wait until its
    maintainer announces itself. Returns the Popen; the caller releases it."""
    argv = [
        *shlex.split(os.environ.get("TAPEDECK_WIKI_CMD", f"{sys.executable} -m wiki")),
        "file",
        NEXT,
    ]
    proc = subprocess.Popen(
        argv,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "TAPEDECK_HOME": str(home)},
    )
    deadline = time.monotonic() + TIMEOUT
    while not (home / "first-running").exists():
        assert proc.poll() is None, proc.communicate()[1]
        assert time.monotonic() < deadline, "the holding maintainer never started"
        time.sleep(0.1)
    return proc


def _release(home, proc):
    (home / "release").touch()
    return proc.communicate(timeout=TIMEOUT)


def test_a_second_filing_refuses_while_one_holds_the_wiki(home, monkeypatch):
    """The race of LESSON-0004, replayed: a filing arrives while another runs.
    It must refuse at once with the lock's message — and the read-only verbs
    must keep working mid-operation, because a diagnosis that queued behind
    every filing would never be run."""
    wiki = filed(home, monkeypatch)
    set_maintainer(home, HOLDS_UNTIL_RELEASED)
    proc = _held_open(home)
    try:
        second = wiki_file(home, NEXT)
        lint = wikilib.run_component("wiki", ["lint"], home)
        dry = wiki_sync(home, "--dry-run")
    finally:
        out, err = _release(home, proc)

    assert second.returncode == 1, f"{second.stdout}\n{second.stderr}"
    assert REFUSAL in second.stderr, (
        f"the refusal names the situation: {second.stderr!r}"
    )
    assert REFUSAL not in lint.stderr, "lint is read-only and takes no lock"
    assert REFUSAL not in dry.stderr and NEXT in dry.stdout, (
        "a dry-run sweep reads without the lock and still sees the unfiled video"
    )

    assert proc.returncode == 0, f"the held filing must land once released:\n{err}"
    assert subjects(wiki)[0] == f"wiki file {NEXT}"
    again = wiki_file(home, NEXT)
    assert again.returncode == 0, "after the dust settles, the refused caller re-runs into a skip"


def test_a_sweep_refuses_the_same_way(home, monkeypatch):
    """`sync` without --dry-run is a mutating operation like any filing: while
    another operation holds the wiki it refuses with the same message instead of
    interleaving its filings between the neighbor's steps."""
    filed(home, monkeypatch)
    set_maintainer(home, HOLDS_UNTIL_RELEASED)
    proc = _held_open(home)
    try:
        sweep = wiki_sync(home)
    finally:
        _release(home, proc)

    assert sweep.returncode == 1, f"{sweep.stdout}\n{sweep.stderr}"
    assert REFUSAL in sweep.stderr, (
        f"the sweep's refusal names the situation: {sweep.stderr!r}"
    )
    assert proc.returncode == 0
