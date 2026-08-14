"""What the library holds — asked in the vocabulary of whoever owns the answer.

LESSON-0003 is the whole design of this module. Whether a name is a video id and
whether an entry holds a downloaded video are ingest's rules (SPEC-ingest-001);
the transcript's filename is transcribe's; the deep-link and timestamp formats
are archive's. Every one of them is imported from its owner, so `add`, `show`,
`list`, `rm` and `retranscribe` cannot answer these questions differently from
the components that do the work — a second copy of a rule is the defect even
while it still agrees.

Nothing here writes. The paths come from system/contracts/library-layout.md,
which every component reads and none of them may rewrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest import VIDEO_ID, videos
from ingest.meta import META_NAME
from transcribe.document import TRANSCRIPT_NAME

from .home import ARCHIVE, LIBRARY

PAGE_SUFFIX = ".md"


def is_video_id(name: str) -> bool:
    """ingest's grammar, not ours (SPEC-ingest-001)."""
    return bool(VIDEO_ID.fullmatch(name or ""))


def entry(home: Path, video_id: str) -> Path:
    return home / LIBRARY / video_id


def page(home: Path, video_id: str) -> Path:
    return home / ARCHIVE / f"{video_id}{PAGE_SUFFIX}"


def media_files(home: Path, video_id: str) -> list[Path]:
    """The downloaded video file(s) of an entry, by ingest's published rule: a
    `video.part` is a fetch in flight and a sidecar is not a video, so neither
    counts here any more than it counts there."""
    return videos(entry(home, video_id))


def media(home: Path, video_id: str) -> Path | None:
    found = media_files(home, video_id)
    return found[0] if found else None


def transcript(home: Path, video_id: str) -> Path | None:
    path = entry(home, video_id) / TRANSCRIPT_NAME
    return path if path.is_file() else None


def names(home: Path) -> list[str]:
    """Every directory under `library/`, in order — including the ones that are
    not videos. A sweep has to know they are there to say it left them alone."""
    library = home / LIBRARY
    if not library.is_dir():
        return []
    return sorted(path.name for path in library.iterdir() if path.is_dir())


def ids(home: Path) -> list[str]:
    """The library entries that are videos, in id order."""
    return [name for name in names(home) if is_video_id(name)]


def known(home: Path, video_id: str) -> bool:
    """Whether tapedeck holds anything at all under this id — an entry, or a page
    left behind by one. `rm` refuses an id it has never heard of."""
    return entry(home, video_id).is_dir() or page(home, video_id).is_file()


def complete(home: Path, video_id: str) -> bool:
    """Whether every link of the derivation chain is already here (SPEC-cli-003).

    This is what makes re-running a 500-video channel affordable: complete means
    the sweep has nothing to do for this video, so it does nothing — no ingest,
    no transcribe, no archive, no index. An entry missing any link is not
    complete, and is re-derived rather than counted as present.
    """
    return (
        media(home, video_id) is not None
        and transcript(home, video_id) is not None
        and page(home, video_id).is_file()
    )


def _document(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def meta(home: Path, video_id: str) -> dict | None:
    """`meta.json` as ingest wrote it, or None if it is not there to be read."""
    return _document(entry(home, video_id) / META_NAME)


def label(home: Path, video_id: str) -> str | None:
    """The model that made this transcript (SPEC-transcribe-001), against which
    supersession is judged. No transcript, or one with no label, is not current
    with any configured model — which is exactly the answer `retranscribe` wants:
    a video with no transcript at all is one it should derive."""
    path = transcript(home, video_id)
    document = _document(path) if path else None
    model = (document or {}).get("model")
    return model if isinstance(model, str) and model.strip() else None
