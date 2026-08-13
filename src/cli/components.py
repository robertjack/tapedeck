"""Delegation to the components that own the work (SPEC-cli-001).

The cli holds no pipeline logic of its own. Every verb that belongs to another
component is that component's module CLI, run as a subprocess at the boundary
its durable evaluations drive — `python -m ingest add|expand`, `python
-m transcribe run|from-parakeet`, `python -m archive render`, `python -m index
update|search`, `python -m ask answer`. Same interpreter, same resolved home, and
the child's exit code is ours unchanged: every component speaks the codes of
contracts/cli-surface.md, so there is nothing to translate. Read-only verbs pass
their stdout straight through — a `--json` payload the cli reformatted would be
the cli's format, not the owner's.

Two things are read out of a component rather than run, both config reads needed
up front: whether a target names one video or a collection
(SPEC-ingest-002 — a channel is a sweep, and `--force` on one has to be refused
before a lister is asked to enumerate it), and which model label the transcriber
seam stamps (SPEC-transcribe-001 — what `retranscribe` judges on).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ingest.sources import COLLECTION, BadRequest, resolve
from transcribe.transcriber import ConfigError, seam

from .home import TRANSCRIPT_NAME, VIDEO_ID, entries, entry, ingested, page

# The derivation chain after the fetch (SPEC-core-002), in the only order it runs:
# transcript from video, page from transcript, index rows from page.
STAGES = (("transcribe", "run"), ("archive", "render"), ("index", "update"))

FORCE_IS_SINGULAR = (
    "--force throws a download away and takes it again; doing that to a whole "
    "playlist or channel has to be deliberate, one `tapedeck add <id> --force` per "
    "video you mean. Without --force this URL is welcome — re-running it picks up "
    "what is new and skips what is here."
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
    """Hand a whole verb over: the component's output is the user's output. With
    nothing captured the child inherits our streams, which is what makes
    `adapt-parakeet` a real filter — stdin to stdout, exit code unchanged."""
    return run(module, args, home).returncode


def last_line(text: str) -> str:
    return ([line.strip() for line in (text or "").splitlines() if line.strip()] or [""])[-1]


def derive(home: Path, video_id: str, force: bool) -> int:
    """transcript → archive page → index rows, for one video already in the library.

    The stages print the artifact they produced; that is progress, not output, so
    the chain keeps it. The first failure ends the chain with that code — nothing
    derives from a link that is not there.
    """
    for module, verb in STAGES:
        args = [verb, video_id]
        # Only transcribe is idempotent-by-skipping in a way that would defeat us:
        # forcing it is how a re-fetch or a model upgrade actually re-derives words.
        if force and module == "transcribe":
            args.append("--force")
        result = run(module, args, home, capture=True)
        if result.returncode != 0:
            return result.returncode
    return 0


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
    """ingest → transcribe → archive → index, for one video. Someone who asked to
    add a video did not ask to read four paths, so only the page is printed."""
    fetched = run("ingest", ["add", target, *(["--force"] if force else [])], home, capture=True)
    if fetched.returncode != 0:
        return fetched.returncode
    video_id = Path(last_line(fetched.stdout)).name
    if not VIDEO_ID.fullmatch(video_id):
        print(f"error: ingest named no entry to build on ({video_id!r})", file=sys.stderr)
        return 1
    # A re-fetched video makes its transcript stale: force the whole chain, or
    # `--force` would leave the old words on the new video.
    code = derive(home, video_id, force)
    if code != 0:
        return code
    print(page(home, video_id))
    return 0


def sweep(home: Path, url: str) -> int:
    """Every video a playlist or channel names, in collection order (SPEC-cli-003).

    A sweep is a long-running thing pointed at a source that changes under it: a
    video may be private or taken down between the listing and the fetch. One of
    those must not cost the user the other ninety-nine, so a failure is reported
    and the sweep goes on; the exit code says whether anything went wrong. Videos
    already here are skipped by ingest itself, which is what makes re-running the
    same channel URL the way to pick up new uploads.
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


def label(home: Path, video_id: str) -> str | None:
    """The model that produced this video's transcript, or None when there is no
    readable transcript to carry a label."""
    try:
        doc = json.loads((entry(home, video_id) / TRANSCRIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc.get("model") if isinstance(doc, dict) else None


def retranscribe(home: Path, dry_run: bool) -> int:
    """A better model regenerates its whole layer (SPEC-core-002), as a verb.

    Supersession is judged on the label alone (SPEC-transcribe-001): a transcript
    stamped with the configured model is current by definition and is not touched,
    which is what makes the sweep a no-op once the library has caught up. A video
    whose transcript is missing or unreadable has no label to match either, so it
    is swept in too — the point of the verb is a library uniformly on the model
    configured now. Failures go the way a collection sweep's do.
    """
    try:
        wanted = seam(home)[1]
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    stale = [video_id for video_id in entries(home) if label(home, video_id) != wanted]
    if dry_run:
        for video_id in stale:
            print(video_id)
        print(f"{len(stale)} video(s) would be re-derived with {wanted}", file=sys.stderr)
        return 0
    done = failed = 0
    for position, video_id in enumerate(stale, start=1):
        print(f"[{position}/{len(stale)}] {video_id} → {wanted}", file=sys.stderr)
        code = derive(home, video_id, force=True)
        if code != 0:
            failed += 1
            print(f"error: {video_id}: failed (exit {code}) — going on", file=sys.stderr)
        else:
            done += 1
    print(f"{done} re-transcribed with {wanted}, {failed} failed")
    return 1 if failed else 0
