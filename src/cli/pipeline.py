"""The verbs that drive the derivation chain: add, retranscribe, rm.

The chain is always the same and always in the same order — ingest, transcribe,
archive, index (SPEC-core-002) — and every step is another component's program.
The cli's own work is deciding *which* videos go through it and what to do when
one of them doesn't make it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ingest import VIDEO
from ingest import resolve as classify
from ingest import video_ids
from transcribe.transcriber import ConfigError, seam

from . import USAGE, Failure, components, library


def _steps(home: Path, steps: list[tuple[str, list[str]]]) -> int:
    """Run a chain, stopping at the first link that fails and keeping its code."""
    for module, args in steps:
        code = components.run(module, args, home, quiet=True)
        if code:
            return code
    return 0


def _render(video_id: str) -> list[tuple[str, list[str]]]:
    """Everything downstream of the transcript: the page, then the rows."""
    return [("archive", ["render", video_id]), ("index", ["update", video_id])]


def _derive(video_id: str) -> list[tuple[str, list[str]]]:
    """Everything downstream of the video itself."""
    return [("transcribe", ["run", video_id]), *_render(video_id)]


def _pipeline(video_id: str, force: bool) -> list[tuple[str, list[str]]]:
    fetch = ["add", video_id] + (["--force"] if force else [])
    return [("ingest", fetch), *_derive(video_id)]


# --- add ---------------------------------------------------------------------


def add(home: Path, target: str, force: bool) -> int:
    """One video, or every video of a playlist or channel (SPEC-cli-003).

    Which of the two it is comes from ingest's URL grammar and nothing else, and
    it is settled before any work starts — including before the lister is asked
    anything, so `--force` on a channel is refused without a network round trip.
    """
    kind, value = classify(target)  # BadRequest for anything that is neither
    if kind == VIDEO:
        return _add_one(home, value, force)
    if force:
        raise Failure(
            "--force re-fetches one video at a time — re-downloading a whole "
            "collection has to be deliberate, so name the videos you mean",
            code=USAGE,
        )
    return _sweep(home, value)


def _add_one(home: Path, video_id: str, force: bool) -> int:
    """The whole chain for one video, refreshing whatever is stale.

    Nothing is skipped here on the cli's say-so: each stage already knows when
    its own artifact is current (ingest skips a download it has, transcribe skips
    a transcript it has), and running the chain is how a lost archive page or a
    dropped index row comes back from a plain `tapedeck add <id>`.
    """
    code = _steps(home, _pipeline(video_id, force))
    if code:
        raise Failure(f"{video_id}: the pipeline did not finish", code=code)
    print(f"{video_id}: {library.page(home, video_id)}")
    return 0


def _sweep(home: Path, url: str) -> int:
    """Every video of a collection, in collection order, one failure at a time.

    Re-running the same URL is the intended way to pick up new uploads, so the
    common case — nothing new — has to cost one listing and nothing else.
    """
    code, listing = components.capture("ingest", ["expand", url], home)
    if code:
        raise Failure(f"could not list {url}", code=code)
    found = video_ids(listing)  # ingest's rule for reading another tool's stdout
    if not found:
        print(f"no videos in {url}", file=sys.stderr)

    added = present = failed = 0
    for position, video_id in enumerate(found, start=1):
        where = f"[{position}/{len(found)}] {video_id}"
        if library.complete(home, video_id):
            present += 1
            print(f"{where}: already present", file=sys.stderr)
            continue
        print(f"{where}: deriving…", file=sys.stderr)
        if _steps(home, _pipeline(video_id, force=False)):
            failed += 1
            # One video's failure is not the sweep's: say which one, and go on.
            print(f"error: {video_id}: failed — continuing the sweep", file=sys.stderr)
        else:
            added += 1

    print(f"{added} added, {present} already present, {failed} failed")
    return 1 if failed else 0


# --- retranscribe ------------------------------------------------------------


def retranscribe(home: Path, dry_run: bool) -> int:
    """SPEC-core-002's "a better model regenerates its whole layer", as a verb.

    Supersession is judged on the transcript's model label against the configured
    one, both read through transcribe (SPEC-transcribe-001) — the component that
    stamps the label decides what the configured model is called.
    """
    try:
        _, model = seam(home)
    except ConfigError as exc:
        raise Failure(str(exc), code=USAGE) from exc

    selected = []
    for name in library.names(home):
        note = _unre_derivable(home, name)
        if note:
            # Selecting these would fail forever and the sweep could never reach
            # the no-op it promises; they are reported and left exactly as they
            # are (SPEC-cli-004).
            print(f"{name}: skipped — {note}", file=sys.stderr)
            continue
        if library.label(home, name) != model:
            selected.append(name)

    if dry_run:
        # A promise of exactly what the sweep would redo: ids on stdout, one per
        # line, nothing else — the skip notes have already gone to stderr.
        for video_id in selected:
            print(video_id)
        return 0
    return _redo(home, selected, model)


def _unre_derivable(home: Path, name: str) -> str | None:
    """Why this entry could never be re-transcribed, or None if it could."""
    if not library.is_video_id(name):
        return "not a video id, so not tapedeck's to touch"
    if library.media(home, name) is None:
        return (
            "no video to re-transcribe from — its media was reclaimed "
            "(`tapedeck add <id> --force` downloads it again)"
        )
    return None


def _redo(home: Path, selected: list[str], model: str) -> int:
    if not selected:
        print(f"nothing to re-transcribe — every transcript is {model}")
        return 0
    failed = 0
    for position, video_id in enumerate(selected, start=1):
        print(f"[{position}/{len(selected)}] {video_id}: re-transcribing…", file=sys.stderr)
        steps = [("transcribe", ["run", video_id, "--force"]), *_render(video_id)]
        if _steps(home, steps):
            failed += 1
            print(f"error: {video_id}: failed — continuing the sweep", file=sys.stderr)
    print(f"{len(selected) - failed} re-transcribed, {failed} failed ({model})")
    return 1 if failed else 0


# --- rm ----------------------------------------------------------------------


def remove(home: Path, video_id: str, media_only: bool) -> int:
    """Forget a video everywhere, or reclaim its disk and keep the knowledge."""
    if not library.is_video_id(video_id):
        raise Failure(f"{video_id!r} is not a video id", code=USAGE)
    if not library.known(home, video_id):
        raise Failure(
            f"no video {video_id} here — `tapedeck list` shows what is", code=USAGE
        )
    if media_only:
        return _reclaim(home, video_id)

    # The page goes before the index is told, so index update sees a video with
    # no archive page — which is how it knows to drop its rows.
    shutil.rmtree(library.entry(home, video_id), ignore_errors=True)
    library.page(home, video_id).unlink(missing_ok=True)
    code = components.run("index", ["update", video_id], home, quiet=True)
    if code:
        raise Failure(f"{video_id}: removed, but the index still knows it", code=code)
    print(f"{video_id}: removed — library entry, archive page and index rows")
    return 0


def _reclaim(home: Path, video_id: str) -> int:
    """Just the video file(s): the transcript, the page and the index stay, and
    the video can never be re-transcribed without downloading it again."""
    removed = library.media_files(home, video_id)
    for path in removed:
        path.unlink(missing_ok=True)
    if not removed:
        print(f"{video_id}: no video file here to reclaim", file=sys.stderr)
    print(f"{video_id}: media removed, knowledge kept ({len(removed)} file(s))")
    return 0
