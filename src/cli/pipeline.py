"""The derivation chain: run for one video, swept over many.

One video is four steps in the order of SPEC-core-002 — ingest, transcribe,
archive, index — each performed by the component with write authority over what
it produces. Nothing here derives anything itself; the cli's only contribution is
the order, and stopping when a link fails rather than deriving a page from a
transcript that was never written.

A sweep is that pipeline over a listing, with the rule that makes re-running a
channel affordable: work already done is not done again. A complete entry costs
the sweep nothing — no ingest, transcribe, archive or index invocation of any
kind — so an unchanged 500-video channel is one listing and a summary line, and
`tapedeck add <channel-url>` is a habit rather than an hour of no-ops. One
video's failure is reported and the sweep continues: a channel is not
all-or-nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import ingest
from transcribe.transcriber import seam

from . import library
from .components import Failed, Usage, capture, step

FORCE_ON_COLLECTION = (
    "--force re-fetches, and a collection re-fetched is a whole channel "
    "downloaded again — deliberate, one video at a time: "
    "`tapedeck add <video-url> --force`"
)


def derive(home: Path, video_id: str, *, force: bool = False) -> None:
    """The whole chain for one video: the video, then everything under it.

    `force` re-fetches, and re-derives what stood on the old bytes with it — a
    transcript of a video that has just been replaced is not a transcript of the
    video that is there now.
    """
    step(home, "ingest", ["add", video_id, *(["--force"] if force else [])], video_id)
    rederive(home, video_id, force=force)


def rederive(home: Path, video_id: str, *, force: bool = False) -> None:
    """The derived layer alone: transcript, archive page, index rows.

    The video is not touched and not asked about — every caller of this has
    already established it is here. That is what makes a better model's sweep
    cost one transcription per video and nothing else (SPEC-core-002).
    """
    step(home, "transcribe", ["run", video_id, *(["--force"] if force else [])], video_id)
    step(home, "archive", ["render", video_id], video_id)
    step(home, "index", ["update", video_id], video_id)


def add(home: Path, target: str, force: bool) -> int:
    """`tapedeck add <url>`: one video, or every video a collection names."""
    kind, value = ingest.resolve(target)  # BadRequest → exit 2, before any work
    if kind == ingest.VIDEO:
        derive(home, value, force=force)
        print(library.page_path(home, value))
        return 0
    if force:
        raise Usage(FORCE_ON_COLLECTION)
    return sweep(home, expand(home, value))


def expand(home: Path, url: str) -> list[str]:
    """The ids a collection names, in the order it names them. ingest owns both
    the listing and the reading of it — a half-read channel is no listing."""
    code, listing = capture(home, "ingest", ["expand", url])
    if code:
        raise Failed(f"could not list {url} (ingest expand exited {code})")
    return ingest.video_ids(listing)


def sweep(home: Path, ids: list[str]) -> int:
    """The pipeline over a collection: skip what is done, report what breaks."""
    if not ids:
        print("that collection listed no videos", file=sys.stderr)
    added = present = failed = 0
    for video_id in ids:
        if library.complete(home, video_id):
            present += 1
            continue
        try:
            derive(home, video_id)
            added += 1
        except Failed as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    print(f"{added} added, {present} already present, {failed} failed")
    return 1 if failed else 0


def retranscribe(home: Path, dry_run: bool) -> int:
    """SPEC-core-002's "a better model regenerates its whole layer", as a verb.

    The configured label is transcribe's answer, not the cli's: `seam` resolves
    the same `[transcribe]` model string that gets stamped on whatever it
    produces, so what this sweep compares against is exactly what the next
    transcript will be labelled with.
    """
    _, model = seam(home)
    redo, skipped = superseded(home, model)
    for note in skipped:
        print(f"skipped {note}", file=sys.stderr)
    if dry_run:
        for video_id in redo:
            print(video_id)
        print(f"{len(redo)} video(s) would be re-transcribed with {model}", file=sys.stderr)
        return 0

    done = failed = 0
    for video_id in redo:
        try:
            rederive(home, video_id, force=True)
            done += 1
        except Failed as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    print(f"{done} re-transcribed with {model}, {failed} failed")
    return 1 if failed else 0


def superseded(home: Path, model: str) -> tuple[list[str], list[str]]:
    """The videos this sweep would redo, and notes on what it left alone.

    Selection is what makes convergence reachable (SPEC-cli-004): only entries the
    sweep could actually re-derive are chosen. A directory that is not a video id
    is not tapedeck's; an entry whose video was reclaimed by `rm --media-only` can
    never be re-transcribed without downloading it again, and choosing it would
    fail the sweep forever. Both are reported and left exactly as they are. What
    remains is every video not already labelled with the configured model —
    including one whose transcript is missing or unreadable, since neither can be
    the label the sweep is converging on.
    """
    redo: list[str] = []
    notes = [f"{name}: not a video id — not tapedeck's to touch" for name in library.foreign(home)]
    for video_id in library.entries(home):
        if library.media(home, video_id) is None:
            notes.append(
                f"{video_id}: no video here to re-transcribe from (reclaimed by "
                "`rm --media-only`?) — its transcript is kept as it is"
            )
            continue
        if not library.has_meta(home, video_id):
            notes.append(f"{video_id}: no meta.json — `tapedeck add {video_id}` restores it")
            continue
        if library.transcript_model(home, video_id) != model:
            redo.append(video_id)
    return redo, sorted(notes)
