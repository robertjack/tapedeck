"""Delegation to the components that own the work (SPEC-cli-001).

The cli holds no pipeline logic of its own. Every verb that belongs to another
component is that component's module CLI, run as a subprocess at exactly the
boundary its durable evaluations drive — `python -m ingest add`, `python -m
transcribe run`, `python -m archive render`, `python -m index update|search`,
`python -m ask answer`. Same interpreter, same resolved home, and the child's
exit code is ours unchanged: every component speaks the codes of
contracts/cli-surface.md, so there is nothing to translate.

Read-only verbs pass their stdout straight through — a `--json` payload the cli
reformatted would be the cli's format, not the component's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .home import VIDEO_ID, page

# The derivation chain after the fetch (SPEC-core-002), in the only order it runs:
# a transcript from the video, a page from the transcript, index rows from the page.
STAGES = (("transcribe", "run"), ("archive", "render"), ("index", "update"))


def run(module: str, args: list[str], home: Path, capture: bool = False):
    """One component boundary, once. Its stderr is the user's either way."""
    sys.stdout.flush()  # ours is line-buffered to a pipe; the child's is not
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        env={**os.environ, "TAPEDECK_HOME": str(home)},
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def delegate(module: str, args: list[str], home: Path) -> int:
    """Hand a whole verb over: the component's output is the user's output."""
    return run(module, args, home).returncode


def last_line(text: str) -> str:
    return ([line.strip() for line in (text or "").splitlines() if line.strip()] or [""])[-1]


def add(home: Path, target: str, force: bool) -> int:
    """ingest → transcribe → archive → index, for one video.

    The stages print the artifact they produced; that is progress, not output —
    someone who asked to add a video did not ask to read four paths — so the
    pipeline keeps them and prints the archive page at the end. The first stage
    to fail ends the run with its own code, because nothing downstream can be
    derived from a link that is not there.
    """
    fetched = run("ingest", ["add", target, *(["--force"] if force else [])], home, capture=True)
    if fetched.returncode != 0:
        return fetched.returncode
    video_id = Path(last_line(fetched.stdout)).name
    if not VIDEO_ID.fullmatch(video_id):
        print(f"error: ingest named no library entry to build on ({video_id!r})", file=sys.stderr)
        return 1

    for module, verb in STAGES:
        args = [verb, video_id]
        # A re-fetched video makes its transcript stale: force the whole chain, not
        # just the download, or `--force` would leave the old words on the new video.
        if force and module == "transcribe":
            args.append("--force")
        result = run(module, args, home, capture=True)
        if result.returncode != 0:
            return result.returncode
    print(page(home, video_id))
    return 0
