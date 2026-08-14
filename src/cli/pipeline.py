"""The verbs that change the library: `add`, `retranscribe`, `rm`.

All three are the derivation chain of SPEC-core-002 driven one video at a time —
ingest, transcribe, archive, index — differing only in where they enter it and
what they choose to skip. The order is not negotiable and the first failing step
ends that video: an archive page rendered from a transcript that was never written
is not a smaller success, it is a wrong answer that search will happily return.

Sweeps here (a collection, a model upgrade) share one shape: decide up front what
is worth doing, do each one independently, and let no single video's failure end
the run. A sweep that stopped at the first bad video would make "re-run the
channel URL" a coin flip instead of a habit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingest import sources
from transcribe import transcriber

from . import Failure, components, library
from .library import Entry


def _chain(home: Path, video_id: str, steps) -> None:
    for module, args in steps:
        code = components.step(module, args, home)
        if code:
            # The child has already said what went wrong on stderr; the exit code
            # is what the cli adds — and a component's usage error (2) is still a
            # usage error when it arrives through here.
            raise Failure(f"{video_id}: {module} {args[0]} failed (exit {code})", code=code)


def derive(home: Path, video_id: str, force: bool = False) -> None:
    """The whole chain for one video: download, transcribe, render, index."""
    _chain(
        home,
        video_id,
        (
            (components.INGEST, ["add", video_id, *(["--force"] if force else [])]),
            (components.TRANSCRIBE, ["run", video_id]),
            (components.ARCHIVE, ["render", video_id]),
            (components.INDEX, ["update", video_id]),
        ),
    )


def rederive(home: Path, video_id: str) -> None:
    """The chain from the transcript down, for a video whose media is already
    here: SPEC-core-002's "a better model regenerates its whole layer" — the new
    transcript is worthless until the page and the rows follow it."""
    _chain(
        home,
        video_id,
        (
            (components.TRANSCRIBE, ["run", video_id, "--force"]),
            (components.ARCHIVE, ["render", video_id]),
            (components.INDEX, ["update", video_id]),
        ),
    )


def add(home: Path, target: str, force: bool) -> int:
    """One video, or every video a collection names (SPEC-cli-003).

    Which of those a URL is, is ingest's reading of it and not a second guess
    here: a watch URL carrying `&list=` is one video, and that rule lives in one
    place (LESSON-0003).
    """
    kind, value = sources.resolve(target)
    if kind == sources.VIDEO:
        derive(home, value, force)
        print(Entry(home, value).page)
        return 0
    if force:
        raise Failure(
            "--force re-fetches one video at a time: name the video rather than "
            f"the collection. Re-fetching everything at {value} must be deliberate",
            code=2,
        )
    return sweep(home, value)


def sweep(home: Path, url: str) -> int:
    """Every video of a collection through the pipeline, in listing order.

    A video that is already complete is skipped whole — no ingest, no transcribe,
    no render, no index update. Re-running an unchanged channel is then one
    listing and nothing else, which is the difference between a habit and an hour.
    """
    ids = expand(home, url)
    print(f"{url}: {len(ids)} video(s)", file=sys.stderr)
    added = present = failed = 0
    for position, video_id in enumerate(ids, 1):
        where = f"[{position}/{len(ids)}] {video_id}"
        if Entry(home, video_id).complete():
            present += 1
            print(f"{where}: already present", file=sys.stderr)
            continue
        print(f"{where}: adding…", file=sys.stderr)
        try:
            derive(home, video_id)
            added += 1
        except Failure as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    print(f"{added} added, {present} already present, {failed} failed")
    return 1 if failed else 0


def expand(home: Path, url: str) -> list[str]:
    """What a collection contains, asked of ingest and read with ingest's own
    parser — a lister's stdout may carry notices and repeats, and which of its
    lines are video ids is not the cli's rule to invent."""
    code, listing = components.output(components.INGEST, ["expand", url], home)
    if code:
        raise Failure(f"could not list {url} (exit {code})", code=code)
    return sources.video_ids(listing)


def select(home: Path, model: str) -> tuple[list[str], list[str]]:
    """The videos a retranscribe sweep can actually redo, and notes on the rest.

    Selecting what it could never finish would put the sweep permanently in
    failure: an entry whose video was reclaimed by `rm --media-only` can never be
    re-transcribed without downloading the video again, and a directory of your
    own under `library/` was never tapedeck's. Both are reported and left exactly
    as they are, so the sweep still converges on a no-op (SPEC-cli-004).
    """
    redo, skipped = [], []
    for path in library.children(home):
        name = path.name
        if not library.is_video_id(name):
            skipped.append(f"{name}: not a video id — leaving it alone")
            continue
        entry = Entry(home, name)
        if not entry.has_media():
            skipped.append(
                f"{name}: no video to re-transcribe from — `tapedeck add {name} "
                "--force` fetches it back first"
            )
            continue
        if entry.model() != model:
            redo.append(name)
    return redo, skipped


def retranscribe(home: Path, dry_run: bool) -> int:
    """Re-derive every transcript a better model supersedes (SPEC-cli-004).

    Supersession is the label, and the label is transcribe's to define: what the
    configured seam would stamp on a transcript made right now is asked of
    transcribe rather than read out of config.toml here.
    """
    _, model = transcriber.seam(home)
    redo, skipped = select(home, model)
    for note in skipped:
        print(f"skipped {note}", file=sys.stderr)
    if dry_run:
        # A promise about the next run, so it lists that and nothing else.
        for video_id in redo:
            print(video_id)
        return 0
    if not redo:
        print(f"every transcript is already {model}", file=sys.stderr)
    done = failed = 0
    for position, video_id in enumerate(redo, 1):
        print(f"[{position}/{len(redo)}] {video_id}: re-deriving with {model}…", file=sys.stderr)
        try:
            rederive(home, video_id)
            done += 1
        except Failure as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    print(f"{done} re-transcribed, {failed} failed")
    return 1 if failed else 0


def remove(home: Path, video_id: str, media_only: bool) -> int:
    """Forget a video, or keep the knowledge and reclaim the disk (SPEC-cli-002).

    Only ever this video's paths: `rm` takes the id it was given to exactly the
    files that id names, and nothing about any other video is opened, let alone
    written.
    """
    entry = Entry(home, video_id)
    if not library.is_video_id(video_id) or not entry.known():
        raise Failure(
            f"no video {video_id!r} in the library — `tapedeck list` shows what is",
            code=2,
        )
    if media_only:
        reclaimed = library.remove_media(entry)
        kept = "transcript, archive page and index kept"
        print(f"{video_id}: {len(reclaimed)} video file(s) deleted — {kept}")
        return 0
    library.remove(entry)
    # The page is gone, so this drops the video's rows; the index owns them and
    # is the only thing that may unmake them.
    if components.step(components.INDEX, ["update", video_id], home):
        raise Failure(
            f"{video_id}: library entry and archive page removed, but the index "
            "still lists it — `tapedeck reindex` rebuilds from what is left"
        )
    print(f"{video_id}: removed — library entry, archive page and index rows")
    return 0
