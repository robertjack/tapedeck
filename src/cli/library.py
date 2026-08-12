"""What is in the library: the reading behind `list` and `show`.

Both read `library/<id>/meta.json` (system/contracts/meta.schema.json) rather
than the index. The question these verbs answer — "what have I got?" — is about
the library itself, so it must stay answerable when tapedeck.db is deleted,
stale, or mid-rebuild; the index is derived, and deriving is not owning.
Read-only: nothing here writes anywhere.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.json"
VIDEO_STEM = "video"
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp")
SUMMARY_KEYS = ("id", "upload_date", "channel", "title", "duration_s", "url")
CHANNEL_COLUMN = 28  # a long channel name pushes its own row out, not every row


class NotInLibrary(ValueError):
    """No such video here — a validation error, not a failed operation."""


class Unreadable(RuntimeError):
    """An entry exists but does not say what it is."""


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, matching the search/ask contracts."""
    try:
        total = max(int(seconds), 0)
    except (TypeError, ValueError):
        return "0:00:00"
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def read_meta(entry: Path) -> dict | None:
    """The entry's metadata, or None when it has none yet (a fetch in flight)."""
    path = entry / META_NAME
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise Unreadable(f"{entry.name}: {META_NAME} is unreadable — {exc}") from exc
    if not isinstance(meta, dict):
        raise Unreadable(f"{entry.name}: {META_NAME} is not a JSON object")
    meta.setdefault("id", entry.name)
    return meta


def find_video(entry: Path) -> Path | None:
    videos = sorted(
        path
        for path in (entry.iterdir() if entry.is_dir() else [])
        if path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO
    )
    return videos[0] if videos else None


def entries(home: Path) -> list[dict]:
    """Every video in the library, newest upload first. One unreadable entry is
    reported and stepped over: a listing that stops at the first bad row is worse
    than a listing with a gap in it."""
    root = home / "library"
    found = []
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        if not entry.is_dir() or entry.name.startswith("."):
            continue  # a dotted dir is a fetch in progress, not a video
        try:
            meta = read_meta(entry)
        except Unreadable as exc:
            print(f"warning: {exc}", file=sys.stderr)
            continue
        if meta is not None:
            found.append(meta)
    found.sort(key=lambda meta: (str(meta.get("upload_date", "")), str(meta["id"])), reverse=True)
    return found


def summary(meta: dict) -> dict:
    return {key: meta.get(key, "") for key in SUMMARY_KEYS}


def listing(metas: list[dict]) -> str:
    """One line per video: id, date, channel, title (contracts/cli-surface.md)."""
    rows = [summary(meta) for meta in metas]
    width = min(max((len(str(row["channel"])) for row in rows), default=0), CHANNEL_COLUMN)
    lines = []
    for row in rows:
        channel = f"{str(row['channel']):<{width}}"
        date = f"{str(row['upload_date']):<10}"
        lines.append(f"{row['id']}  {date}  {channel}  {row['title']}".rstrip())
    return "\n".join(lines)


def locate(home: Path, video_id: str) -> tuple[dict, dict, list[str]]:
    """One video's metadata, where its artifacts live, and which are not there."""
    if not VIDEO_ID.fullmatch(video_id):
        raise NotInLibrary(f"{video_id!r} is not an 11-character video id")
    entry = home / "library" / video_id
    meta = read_meta(entry) if entry.is_dir() else None
    if meta is None:
        raise NotInLibrary(f"{video_id}: not in the library ({home / 'library'})")
    video = find_video(entry)
    paths = {
        "entry": str(entry),
        "video": str(video) if video else None,
        "transcript": str(entry / TRANSCRIPT_NAME),
        "archive": str(home / "archive" / f"{video_id}.md"),
    }
    missing = [name for name in ("transcript", "archive") if not Path(paths[name]).is_file()]
    if video is None:
        missing.append("video")
    return meta, paths, missing


def detail(meta: dict, paths: dict, missing: list[str]) -> str:
    """Metadata and the artifact paths — including the ones not written yet, so
    `show` says where a missing transcript or page *would* be."""
    facts = " · ".join(
        part
        for part in (meta.get("channel"), meta.get("upload_date"), hms(meta.get("duration_s")))
        if part
    )
    lines = [f"{meta['id']}  {meta.get('title', '')}".rstrip()]
    for line in (facts, meta.get("url", "")):
        if line:
            lines.append(line)
    lines.append("")
    for name in ("video", "transcript", "archive"):
        where = paths[name] or f"{paths['entry']}/{VIDEO_STEM}.<ext>"
        note = "  (missing)" if name in missing else ""
        lines.append(f"{name:<11} {where}{note}")
    chapters = meta.get("chapters")
    if isinstance(chapters, list) and chapters:
        lines.append(f"{'chapters':<11} {len(chapters)}")
    return "\n".join(lines)
