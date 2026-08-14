"""The library as the cli reads it, in the vocabulary of whoever owns each answer.

Four questions run through `add`, `show`, `list`, `rm` and `retranscribe`: is this
an id, is the video here, is this entry finished, what model made its transcript.
Not one of them is the cli's to answer. The id grammar and what counts as a
downloaded video are ingest's (SPEC-ingest-001) — `video.part` is a fetch in
flight, and only ingest gets to say so; the transcript's name is transcribe's; the
archive page's location is the layout contract's. Imported, so a verb here can
never reach a different verdict from the component that writes the file
(LESSON-0003).

Reading only: every path this module deletes belongs to `rm`, which is the one
verb licensed to unmake what other components made (SPEC-cli-002).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ingest.fetch import has_video, videos
from ingest.meta import META_NAME
from ingest.sources import VIDEO_ID
from transcribe.document import TRANSCRIPT_NAME

from .home import ARCHIVE, LIBRARY


def is_video_id(text: str) -> bool:
    """ingest's grammar, asked rather than repeated."""
    return bool(VIDEO_ID.fullmatch(text or ""))


@dataclass(frozen=True)
class Entry:
    """One video's files, wherever they live in the layout."""

    home: Path
    video_id: str

    @property
    def path(self) -> Path:
        return self.home / LIBRARY / self.video_id

    @property
    def page(self) -> Path:
        return self.home / ARCHIVE / f"{self.video_id}.md"

    @property
    def meta_path(self) -> Path:
        return self.path / META_NAME

    @property
    def transcript_path(self) -> Path:
        return self.path / TRANSCRIPT_NAME

    def media(self) -> Path | None:
        """The downloaded video, by ingest's rule — a part-file is not one."""
        found = videos(self.path)
        return found[0] if found else None

    def has_media(self) -> bool:
        return has_video(self.path)

    def known(self) -> bool:
        """Has this id anything in the library at all? `rm` refuses ids that
        name nothing, and an entry stripped by `rm --media-only` still counts."""
        return self.path.is_dir() or self.page.is_file()

    def complete(self) -> bool:
        """Nothing `add` could do for this video that is not already done: the
        video itself, its metadata, its transcript, its page. This is what a
        collection sweep skips on, so it is the difference between re-running a
        500-video channel for one listing and re-running it for two thousand
        no-ops (SPEC-cli-003)."""
        return (
            self.has_media()
            and self.meta_path.is_file()
            and self.transcript_path.is_file()
            and self.page.is_file()
        )

    def meta(self) -> dict:
        return _document(self.meta_path)

    def model(self) -> str | None:
        """The transcript's model label — what supersession is judged on
        (SPEC-transcribe-001). No transcript and no label are the same answer
        here: neither is the configured model, so both are re-derived."""
        label = _document(self.transcript_path).get("model")
        return label if isinstance(label, str) and label.strip() else None


def _document(path: Path) -> dict:
    """A JSON object on disk, or nothing. An unreadable file is a video that
    tells us less, never a crashed verb."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def children(home: Path) -> list[Path]:
    """Every directory under `library/`, ids and strangers alike — the sweep in
    SPEC-cli-004 has to see what it is choosing not to touch."""
    root = home / LIBRARY
    return sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []


def entries(home: Path) -> list[Entry]:
    return [Entry(home, path.name) for path in children(home) if is_video_id(path.name)]


def remove(entry: Entry) -> None:
    """Everything the library holds for one video, except its rows — those are
    the index's to drop, once its page is gone."""
    shutil.rmtree(entry.path, ignore_errors=True)
    entry.page.unlink(missing_ok=True)


def remove_media(entry: Entry) -> list[Path]:
    """Just the video file(s): the disk back, the knowledge kept. What is a video
    file is ingest's rule again, so this reclaims exactly what `add` fetched."""
    removed = []
    for path in videos(entry.path):
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed
