"""The library as ask sees it: which videos are here, and how long each one runs.

Read-only, and the whole of what ask knows about `library/<id>/meta.json`
(system/contracts/library-layout.md). Is there anything to answer from, is
`--video <id>` real, is this citation's moment real — all from metadata alone.

Every question about a video *id* is asked of one path (SPEC-ask-003): a library
grows without bound, and enumerating it to learn whether one id is in it is a scan
the answer never needed. A local citation breaks that shortcut on purpose — its id is
a digest of the file's bytes (SPEC-ingest-005), not derivable from the path a citation
names, so the only way back from a path to an entry is the address that entry wrote
for itself in meta.json, and finding it costs a scan. `stocked` and `resolve_local`
are the two places that scan; everything else is one lookup.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
LIBRARY = "library"
META_NAME = "meta.json"


def _duration(meta) -> int | None:
    """A video's length in seconds, or None when the library does not know it.

    `duration_s: 0` is what ingest writes when the source withheld the duration
    (contracts/ask-citations.md): unknown, not zero seconds long. Read as a real
    length it would put every moment past the end of the video, so a truthful
    citation would be reported as a fabrication.
    """
    try:
        seconds = int(float(meta["duration_s"]))
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return seconds if seconds > 0 else None


class Library:
    """One home's `library/`, answering per-video questions and remembering answers.

    An answer cites the same video many times over; the facts behind it are read
    once per id, then held for the length of the run.
    """

    def __init__(self, home: Path):
        self.root = home / LIBRARY
        self._facts: dict[str, tuple[bool, int | None]] = {}
        self._locals: dict[str, str] | None = None

    def _entries(self):
        return self.root.iterdir() if self.root.is_dir() else ()

    def _read(self, video_id: str) -> tuple[bool, int | None]:
        if not VIDEO_ID.fullmatch(video_id):
            return False, None
        entry = self.root / video_id
        if not entry.is_dir():
            return False, None
        try:
            meta = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Present but illegible: being here is what makes a citation real, and
            # the length only bounds it — an unreadable meta.json bounds nothing.
            return True, None
        return True, _duration(meta) if isinstance(meta, dict) else None

    def facts(self, video_id: str) -> tuple[bool, int | None]:
        if video_id not in self._facts:
            self._facts[video_id] = self._read(video_id)
        return self._facts[video_id]

    def holds(self, video_id: str) -> bool:
        """Is this video in the library? One directory, one question."""
        return self.facts(video_id)[0]

    def duration(self, video_id: str) -> int | None:
        """How long it runs, where that is known — None bounds nothing."""
        return self.facts(video_id)[1]

    def stocked(self) -> bool:
        """Is there anything at all to answer from? Stops at the first video."""
        return any(e.is_dir() and VIDEO_ID.fullmatch(e.name) for e in self._entries())

    def _local_index(self) -> dict[str, str]:
        """path -> video_id for every local entry, built once and held for the run."""
        if self._locals is None:
            index: dict[str, str] = {}
            for entry in self._entries():
                if not (entry.is_dir() and VIDEO_ID.fullmatch(entry.name)):
                    continue
                try:
                    meta = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                url = meta.get("url") if isinstance(meta, dict) else None
                if isinstance(url, str) and url.startswith("file://"):
                    index[urlsplit(url).path] = entry.name
            self._locals = index
        return self._locals

    def resolve_local(self, path: str) -> str | None:
        """The library entry whose own address names this path, if any
        (contracts/ask-citations.md: "resolved to its entry by the path it names")."""
        return self._local_index().get(path)
