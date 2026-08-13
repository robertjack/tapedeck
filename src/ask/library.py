"""The library as ask sees it: which videos exist, and how long each one runs.

Read-only, and the whole of what ask knows about `library/<id>/meta.json`
(system/contracts/library-layout.md). Two questions are asked of it — is there
anything to answer from at all, and is this citation's moment a real one — and
both are answered from metadata alone, never from the video or the transcript.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
META_NAME = "meta.json"


def _duration(meta) -> int | None:
    try:
        return int(float(meta["duration_s"]))
    except (TypeError, ValueError, KeyError):
        return None


def videos(home: Path) -> dict[str, int | None]:
    """Every ingested video id, mapped to its duration in seconds where known.

    An entry whose meta.json is missing or unreadable still counts as present: being
    in the library is what makes a citation real, and knowing the length only bounds
    it — a metadata gap is not grounds for calling a citation fabricated.
    """
    root = home / "library"
    found: dict[str, int | None] = {}
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        if not entry.is_dir() or not VIDEO_ID.fullmatch(entry.name):
            continue
        try:
            meta = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        found[entry.name] = _duration(meta) if isinstance(meta, dict) else None
    return found
