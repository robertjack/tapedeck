"""Delegation to the components that own the work (SPEC-cli-001).

The cli holds no pipeline logic of its own. Every verb that belongs to another
component is that component's module CLI, run as a subprocess at exactly the
boundary its durable evaluations drive — `python -m ingest add|expand`, `python
-m transcribe run`, `python -m archive render`, `python -m index update|search`,
`python -m ask answer`. Same interpreter, same resolved home, and the child's
exit code is ours unchanged: every component speaks the codes of
contracts/cli-surface.md, so there is nothing to translate.

Read-only verbs pass their stdout straight through — a `--json` payload the cli
reformatted would be the cli's format, not the component's.

One thing is read out of ingest rather than run: whether a target names a single
video or a collection. That reading is ingest's own (SPEC-ingest-002) and costs
no network, and the cli needs the answer before it does anything — one video is
a pipeline, a channel is a sweep, and `--force` on a channel has to be refused
before a lister is ever asked to enumerate it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ingest.sources import COLLECTION, BadRequest, resolve

from .home import VIDEO_ID, ingested, page

# The derivation chain after the fetch (SPEC-core-002), in the only order it runs:
# a transcript from the video, a page from the transcript, index rows from the page.
STAGES = (("transcribe", "run"), ("archive", "render"), ("index", "update"))

FORCE_IS_SINGULAR = (
    "--force throws away a download and takes it again, and doing that to an entire "
    "playlist or channel has to be deliberate: name the videos you mean, one "
    "`tapedeck add <id> --force` each. Without --force this URL is welcome — "
    "re-running it picks up whatever is new and skips what is already here."
)


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
    """`tapedeck add <url>`: one video, or every video a collection names."""
    try:
        kind, _ = resolve(target)
    except BadRequest as exc:  # not a video and not a collection — nothing to add
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if kind != COLLECTION:
        return add_one(home, target, force)
    if force:
        print(f"error: {FORCE_IS_SINGULAR}", file=sys.stderr)
        return 2
    return sweep(home, target)


def add_one(home: Path, target: str, force: bool) -> int:
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


def sweep(home: Path, url: str) -> int:
    """Every video a playlist or channel names, in collection order (SPEC-cli-003).

    A sweep is a long-running thing pointed at a source that changes under it: a
    video may be private, region-locked, or taken down between the listing and the
    fetch. One of those must not cost the user the other ninety-nine, so a failure
    is reported and the sweep goes on, and the exit code at the end says whether
    anything went wrong. Videos already here are skipped by ingest itself, which is
    what makes re-running the same channel URL the way to pick up new uploads.
    """
    listed = run("ingest", ["expand", url], home, capture=True)
    if listed.returncode != 0:
        # Half a channel passed off as the whole one is the failure worth refusing:
        # if the listing is not trustworthy, there is no sweep to run.
        return listed.returncode
    ids = [
        token
        for token in (line.strip() for line in (listed.stdout or "").splitlines())
        if VIDEO_ID.fullmatch(token)
    ]
    added = skipped = failed = 0
    for position, video_id in enumerate(ids, start=1):
        here = ingested(home, video_id)
        print(f"[{position}/{len(ids)}] {video_id}", file=sys.stderr)
        code = add_one(home, video_id, force=False)
        if code != 0:
            failed += 1
            print(f"error: {video_id}: failed (exit {code}) — going on", file=sys.stderr)
        elif here:
            skipped += 1
        else:
            added += 1
    print(f"{added} added, {skipped} already present, {failed} failed")
    return 1 if failed else 0
