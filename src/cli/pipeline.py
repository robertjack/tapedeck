"""The derivation chain as a verb: `add` and `retranscribe`.

One video is derived by running the four owners in order — ingest, transcribe,
archive, index (SPEC-core-002). Both sweeps here are built for repetition rather
than for a first run: one video's failure is reported and the sweep goes on
(SPEC-cli-003, SPEC-cli-004), so a channel of five hundred videos is not held
hostage by one that has been taken down, and running it again is how the rest
catch up.

What the sweeps refuse to do is as important as what they do. `add` on an
unchanged collection derives nothing at all — no ingest, transcribe, archive or
index invocation for a video that is already complete — because a re-derivation
that lands identical bytes still costs two thousand subprocesses on a big
channel, and that is the difference between "re-run the channel URL" being a
habit and being an hour. `retranscribe` selects only what it could actually
re-derive, so a library holding entries whose media was reclaimed still converges
on a no-op instead of failing forever.

After each video's chain succeeds, and before the sweep moves on, that id is
filed into the wiki (SPEC-cli-009) — as each video completes rather than in one
pass at the end, so an interrupted channel leaves a wiki that matches the part of
the library it managed to build. The filing is `wiki file <id>` itself, at the
component's boundary like every stage above it, and it is best-effort by
specification: a rejected gate, a crashed maintainer or a seam nobody configured
costs one note on stderr and nothing else. Not the exit code, not the summary's
counts, not the sweep, and nothing on stdout at all. The video is downloaded,
transcribed, rendered and indexed — which is what `add` was asked for and what
cost the bandwidth — and a page that did not get written is a `tapedeck wiki
sync` away at any later moment.

Every question about an entry is asked of the component that owns the answer
(LESSON-0003): whether a name is a video id and whether the media is really there
are ingest's, and the model label supersession is judged on is transcribe's.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import ingest
from transcribe.transcriber import seam

from . import Failure, Usage, components, doctor
from .home import ARCHIVE, AUTO_FILE_DEFAULT, LIBRARY, WIKI

# Names pinned by system/contracts/library-layout.md, which the cli reads as
# directly as any other component does.
META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.json"

CHAIN = (("transcribe", ["run"]), ("archive", ["render"]), ("index", ["update"]))

AUTO_KEY = "auto"
MAINTAINER_KEY = "maintainer_command"


def entry_of(home: Path, video_id: str) -> Path:
    return home / LIBRARY / video_id


def page_of(home: Path, video_id: str) -> Path:
    return home / ARCHIVE / f"{video_id}.md"


def derive(home: Path, video_id: str, force: bool = False) -> None:
    """ingest -> transcribe -> archive -> index, for one video. Raises on a break.

    Each stage is idempotent on its own (SPEC-core-003): ingest skips a download
    it already has, transcribe skips a transcript it already has, and the last two
    are pure re-renders. So this is safe to run on a half-derived entry, and it is
    what fills whichever link is missing.
    """
    stages = [("ingest", ["add", video_id, *(["--force"] if force else [])])]
    stages += [(module, [*args, video_id]) for module, args in CHAIN]
    for module, args in stages:
        code = components.stage(module, args, home)
        if code:
            raise Failure(f"{video_id}: {module} failed (exit {code})")


def complete(home: Path, video_id: str) -> bool:
    """Is every link of this video's chain already here? The media question is
    ingest's — an entry holding only `video.part` has a fetch in flight, not a
    video, and answering it any other way would skip a download that never
    finished."""
    entry = entry_of(home, video_id)
    return (
        ingest.has_video(entry)
        and (entry / META_NAME).is_file()
        and (entry / TRANSCRIPT_NAME).is_file()
        and page_of(home, video_id).is_file()
    )


def auto_filing(home: Path) -> bool:
    """`[wiki] auto`, where an absent key reads exactly what the first-run
    scaffold writes down (SPEC-cli-009). One default, in one place: a config
    written before the key existed must not mean the opposite of the shipped
    file. Anything that is not a boolean is not an answer to this question, so
    it reads as the default too."""
    settings, _ = doctor.config(home)
    section = settings.get(WIKI)
    value = section.get(AUTO_KEY) if isinstance(section, dict) else None
    return value if isinstance(value, bool) else AUTO_FILE_DEFAULT


def seam_note(home: Path) -> str:
    """Where the failure was the seam, say the seam — a note that only says
    something went wrong sends the user searching a library that is complete."""
    settings, _ = doctor.config(home)
    command = doctor.setting(settings, WIKI, MAINTAINER_KEY)
    if not command:
        return f"[{WIKI}].{MAINTAINER_KEY} is not set in config.toml"
    tool = doctor.head(command)
    if tool and not shutil.which(tool):
        return f"[{WIKI}].{MAINTAINER_KEY} names {tool}, which is not on PATH"
    return ""


def file_into_wiki(home: Path, video_id: str) -> None:
    """The epilogue. With `auto = false` it does not happen at all — no
    maintainer, no note, no mention of a wiki — because silence is the whole
    content of that request.

    Nothing below can raise into `add`. Best-effort is the specification, and a
    filing that could not even be attempted is the same kind of nothing as one
    the gate refused: a note, and the sweep goes on."""
    if not auto_filing(home):
        return
    try:
        code = components.stage(WIKI, ["file", video_id], home)
        reason = f"wiki exited {code}" if code else ""
    except OSError as exc:
        reason = f"the wiki component could not be run — {exc}"
    if not reason:
        return
    seam = seam_note(home)
    print(
        f"note: the wiki filing for {video_id} failed ({reason}"
        f"{f'; {seam}' if seam else ''}) — the video itself is added, transcribed, "
        f"archived and indexed; `tapedeck wiki sync` files it whenever you like",
        file=sys.stderr,
    )


def expand(home: Path, url: str) -> list[str]:
    """The video ids a collection URL names, in the collection's own order."""
    code, listing = components.capture("ingest", ["expand", url], home)
    if code:
        raise Failure(f"could not list {url} — ingest exited {code}")
    return ingest.video_ids(listing)


def add(home: Path, target: str, force: bool) -> int:
    """One video, or every video a playlist or channel names (SPEC-cli-003)."""
    kind, value = ingest.resolve(target)  # BadRequest is a usage error, exit 2
    if kind == ingest.COLLECTION:
        if force:
            raise Usage(
                "--force on a collection is refused: re-fetching a whole channel "
                "must be deliberate, one video at a time (`tapedeck add <id> --force`)"
            )
        return sweep(home, expand(home, value), skip_complete=True)
    # A single video is always re-derived, never skipped: it is how a lost
    # archive page or a lost index row comes back (SPEC-core-002).
    return sweep(home, [value], skip_complete=False, force=force)


def sweep(home: Path, ids, *, skip_complete: bool, force: bool = False) -> int:
    added = skipped = failed = 0
    for video_id in ids:
        if skip_complete and complete(home, video_id):
            skipped += 1
            continue
        try:
            derive(home, video_id, force)
            added += 1
        except Failure as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
            continue
        file_into_wiki(home, video_id)
    print(f"{added} added, {skipped} already present, {failed} failed")
    return 1 if failed else 0


def label(entry: Path) -> str | None:
    """The model that made this transcript, or None if there is no transcript to
    read. None is not "current": a video whose transcript went missing is one the
    sweep can put back, which is what makes `retranscribe` the recovery verb."""
    try:
        document = json.loads((entry / TRANSCRIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document.get("model") if isinstance(document, dict) else None


def superseded(home: Path, model: str) -> list[str]:
    """The videos this sweep would redo, and a note on stderr for each entry it
    cannot (SPEC-cli-004). Anything under `library/` that is not a well-formed id,
    or whose media is gone, could never be re-transcribed without downloading the
    video again — selecting it would mean the sweep never reaches a no-op."""
    library = home / LIBRARY
    stale = []
    for entry in sorted(library.iterdir()) if library.is_dir() else []:
        if not entry.is_dir():
            continue
        video_id = entry.name
        if not ingest.VIDEO_ID.fullmatch(video_id):
            print(f"{video_id}: not a video id — skipped, it is not tapedeck's", file=sys.stderr)
        elif not ingest.has_video(entry):
            print(
                f"{video_id}: no video file — skipped; its transcript can only be "
                f"redone by fetching the video again (`tapedeck add {video_id}`)",
                file=sys.stderr,
            )
        elif label(entry) != model:
            stale.append(video_id)
    return stale


def redo(home: Path, video_id: str) -> None:
    """SPEC-core-002's "a better model regenerates its whole layer": the transcript
    is forced, and everything derived from it follows."""
    stages = [("transcribe", ["run", video_id, "--force"])]
    stages += [(module, [*args, video_id]) for module, args in CHAIN[1:]]
    for module, args in stages:
        code = components.stage(module, args, home)
        if code:
            raise Failure(f"{video_id}: {module} failed (exit {code})")


def retranscribe(home: Path, dry_run: bool) -> int:
    _, model = seam(home)  # transcribe owns the label; ConfigError is exit 2
    stale = superseded(home, model)
    if dry_run:
        for video_id in stale:
            print(video_id)
        return 0
    failed = 0
    for video_id in stale:
        try:
            redo(home, video_id)
        except Failure as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    print(f"{len(stale) - failed} retranscribed, {failed} failed ({model})")
    return 1 if failed else 0
