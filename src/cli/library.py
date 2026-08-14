"""What the library holds, asked in the vocabulary of whoever owns the answer.

Every question below has an owner, and the owner is imported (LESSON-0003):
`ingest.VIDEO_ID` decides what a video id is, `ingest.videos` / `ingest.has_video`
decide whether an entry holds a downloaded video — `video.part` is a fetch in
flight and never the video — and `ingest.meta.META_NAME` and
`transcribe.document.TRANSCRIPT_NAME` are the names their writers write. The cli
restates none of them; it composes them into the one question that is its own:
is this entry complete, so that a sweep can skip it and cost nothing?
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest import VIDEO_ID, has_video, videos
from ingest.meta import META_NAME
from transcribe.document import TRANSCRIPT_NAME

from .home import ARCHIVE, LIBRARY

PAGE_SUFFIX = ".md"


def is_video_id(text: str) -> bool:
    return bool(VIDEO_ID.fullmatch(text or ""))


def entry_dir(home: Path, video_id: str) -> Path:
    return home / LIBRARY / video_id


def page_path(home: Path, video_id: str) -> Path:
    return home / ARCHIVE / f"{video_id}{PAGE_SUFFIX}"


def media_files(home: Path, video_id: str) -> list[Path]:
    """The downloaded video files in an entry, by ingest's rule — the files
    `rm --media-only` reclaims, and nothing that merely sits beside them."""
    return videos(entry_dir(home, video_id))


def media(home: Path, video_id: str) -> Path | None:
    """The downloaded video of an entry, or None if there is none — which is also
    what tells the reader that `add` would fetch it again."""
    found = media_files(home, video_id)
    return found[0] if found else None


def entries(home: Path) -> list[str]:
    """Every video in the library, in id order."""
    return [name for name, _ in _directories(home) if is_video_id(name)]


def _directories(home: Path) -> list[tuple[str, Path]]:
    library = home / LIBRARY
    contents = sorted(library.iterdir()) if library.is_dir() else []
    # Dot-prefixed directories are somebody's work in progress — ingest stages a
    # download in one — and are not the library's to report on either way.
    return [(p.name, p) for p in contents if p.is_dir() and not p.name.startswith(".")]


def foreign(home: Path) -> list[str]:
    """Directories under `library/` that are not videos at all. A sweep leaves
    them alone and says so, rather than failing on them forever."""
    return [name for name, _ in _directories(home) if not is_video_id(name)]


def read_json(path: Path) -> dict | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def meta(home: Path, video_id: str) -> dict | None:
    return read_json(entry_dir(home, video_id) / META_NAME)


def transcript(home: Path, video_id: str) -> dict | None:
    return read_json(entry_dir(home, video_id) / TRANSCRIPT_NAME)


def transcript_model(home: Path, video_id: str) -> str | None:
    """The model a transcript is labelled with — the string supersession is judged
    on (SPEC-transcribe-001). None when there is no transcript to judge."""
    document = transcript(home, video_id) or {}
    label = document.get("model")
    return label if isinstance(label, str) and label.strip() else None


def has_meta(home: Path, video_id: str) -> bool:
    return (entry_dir(home, video_id) / META_NAME).is_file()


def complete(home: Path, video_id: str) -> bool:
    """Whether the whole derivation chain is already on disk for this video.

    This is what a collection sweep skips on (SPEC-cli-003), so it asks about
    every link: the video by ingest's rule, its metadata, its transcript, its
    archive page. An entry holding only a partial download is not complete, and
    an entry missing any derived artifact is not either — both get re-derived,
    and everything else costs the sweep nothing at all.
    """
    entry = entry_dir(home, video_id)
    return (
        has_video(entry)
        and (entry / META_NAME).is_file()
        and (entry / TRANSCRIPT_NAME).is_file()
        and page_path(home, video_id).is_file()
    )
