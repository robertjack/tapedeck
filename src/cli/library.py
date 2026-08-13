"""What the cli reads from the library, and what `rm` takes away.

`list` and `show` answer from `library/<id>/meta.json` rather than from the
index: a video is in the library the moment ingest has written it, index or no
index, and those two verbs should say so.

Removal (SPEC-cli-002) is the one place the cli touches paths another component
writes — the layout contract gives `rm` no other owner. It still stops short of
`tapedeck.db`: the cli takes the archive page away and lets the index component
notice, so the database keeps exactly one writer (SPEC-core-001).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
VIDEO_STEM = "video"
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp")
UNITS = ("B", "KB", "MB", "GB", "TB")


def entry(home: Path, video_id: str) -> Path:
    return home / "library" / video_id


def page(home: Path, video_id: str) -> Path:
    return home / "archive" / f"{video_id}.md"


def is_media(path: Path) -> bool:
    """`video.<ext>` — the download itself, as the layout contract names it."""
    return path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO


def media(home: Path, video_id: str) -> list[Path]:
    directory = entry(home, video_id)
    return sorted(p for p in directory.iterdir() if is_media(p)) if directory.is_dir() else []


def read_meta(home: Path, video_id: str) -> dict | None:
    """The video's metadata, or None if there is no readable entry here."""
    try:
        data = json.loads((entry(home, video_id) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def known(home: Path, video_id: str) -> bool:
    """Anything of this video still on disk — an entry, or a page left behind."""
    return entry(home, video_id).is_dir() or page(home, video_id).is_file()


def row(video_id: str, meta: dict) -> dict:
    """The four things `list` shows, present and stringy whatever meta.json holds."""
    def text(key):
        value = meta.get(key)
        return value if isinstance(value, str) else ""

    return {
        "id": video_id,
        "upload_date": text("upload_date"),
        "channel": text("channel"),
        "title": text("title") or video_id,
    }


def videos(home: Path) -> list[dict]:
    """Every ingested video, newest upload first. A directory with no readable
    meta.json is not an ingested video yet, so it is not one of these."""
    library = home / "library"
    found = [
        row(d.name, meta)
        for d in (library.iterdir() if library.is_dir() else [])
        if d.is_dir() and not d.name.startswith(".") and (meta := read_meta(home, d.name))
    ]
    return sorted(found, key=lambda v: (v["upload_date"], v["id"]), reverse=True)


def delete_media(home: Path, video_id: str) -> list[tuple[str, int]]:
    """Drop the download, keep everything derived from it (SPEC-cli-002).
    Returns what went, and how big it was — reclaimed disk is the whole point."""
    removed = []
    for path in media(home, video_id):
        removed.append((path.name, path.stat().st_size))
        path.unlink()
    return removed


def delete_page(home: Path, video_id: str) -> None:
    page(home, video_id).unlink(missing_ok=True)


def delete_entry(home: Path, video_id: str) -> None:
    directory = entry(home, video_id)
    if directory.is_dir():
        shutil.rmtree(directory)


def clock(seconds) -> str:
    """h:mm:ss, the way timestamps read everywhere else in tapedeck."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0:
        return "?"
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def size(nbytes: float) -> str:
    for unit in UNITS:
        if nbytes < 1024 or unit == UNITS[-1]:
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024
