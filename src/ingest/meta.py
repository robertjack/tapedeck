"""The fetcher's info.json → meta.json (system/contracts/meta.schema.json).

Source metadata is whatever the fetcher hands us; meta.json is the shape every
downstream component reads. So normalization happens exactly here — dates become
ISO, durations become whole seconds, chapters become {title, start_s} — and only
the schema's own properties are carried through: fields nobody agreed on must
not reach the archive renderer as if they had been.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .sources import watch_url

META_NAME = "meta.json"
INFO_NAME = "info.json"  # what the pinned fetcher interface writes
INFO_GLOB = "*.info.json"  # what `yt-dlp --write-info-json` writes


class BadMetadata(ValueError):
    """The fetcher's metadata cannot be normalized into meta.json."""


def find_info(dest: Path) -> Path:
    direct = dest / INFO_NAME
    if direct.is_file():
        return direct
    candidates = sorted(path for path in dest.glob(INFO_GLOB) if path.is_file())
    if not candidates:
        raise BadMetadata(f"the fetcher wrote no {INFO_NAME} in {dest}")
    return candidates[0]


def read_info(path: Path) -> dict:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BadMetadata(f"{path.name} is unreadable — {exc}") from exc
    if not isinstance(info, dict):
        raise BadMetadata(f"{path.name} is not a JSON object")
    return info


def _number(value):
    """The value as a float, or None for anything that is not a plain number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _upload_date(info: dict) -> str:
    """YYYYMMDD (or an epoch) → YYYY-MM-DD; the schema takes nothing else."""
    for key in ("upload_date", "release_date"):
        digits = str(info.get(key) or "").replace("-", "")
        try:
            return datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            continue
    for key in ("timestamp", "release_timestamp"):
        stamp = _number(info.get(key))
        if stamp is not None:
            return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d")
    raise BadMetadata("the fetcher's metadata has no usable upload_date")


def _duration_s(info: dict) -> int:
    """Whole seconds; a source without a duration (a live stream) reports 0."""
    seconds = _number(info.get("duration"))
    try:
        return max(0, round(seconds))
    except (TypeError, ValueError, OverflowError):
        return 0


def _chapters(info: dict) -> list[dict]:
    chapters = []
    source = info.get("chapters")
    for raw in source if isinstance(source, list) else []:
        start = _number(raw.get("start_time")) if isinstance(raw, dict) else None
        if start is None:
            continue  # a chapter we cannot place is worse than no chapter at all
        start = max(0.0, start)
        chapters.append(
            {
                "title": str(raw.get("title") or ""),
                "start_s": int(start) if start.is_integer() else start,
            }
        )
    return chapters


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize(video_id: str, info: dict, ingested_at: str | None = None) -> dict:
    """info.json as meta.json: required keys first, optional ones only when real."""
    meta = {
        "id": video_id,
        "title": str(info.get("title") or video_id),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "upload_date": _upload_date(info),
        "duration_s": _duration_s(info),
        "url": str(info.get("webpage_url") or watch_url(video_id)),
    }
    description = info.get("description")
    if isinstance(description, str) and description:
        meta["description"] = description
    chapters = _chapters(info)
    if chapters:
        meta["chapters"] = chapters
    meta["ingested_at"] = ingested_at or _now()
    return meta


def write(dest: Path, meta: dict) -> Path:
    path = dest / META_NAME
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
