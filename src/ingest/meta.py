"""The fetcher's info.json → library/<id>/meta.json (contracts/meta.schema.json).

A fetcher emits whatever its tool happens to know: a hundred keys, dates as
`20260115`, chapters keyed `start_time`, durations as floats. meta.json is the
shape every other component reads, so the narrowing happens exactly here — the
schema's own properties and nothing else (`additionalProperties: false`), dates
as YYYY-MM-DD, seconds as numbers. Downstream never sees yt-dlp's vocabulary.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

META_NAME = "meta.json"
COMPACT_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})")
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")  # a full timestamp keeps its date


class BadMeta(ValueError):
    """The fetcher's metadata cannot be normalized into meta.json."""


def _text(value) -> str:
    """A string field as the schema wants it: a real string, or nothing."""
    return value.strip() if isinstance(value, str) else ""


def _line(value) -> str:
    """One-line fields (title, chapter names) with their whitespace tidied."""
    return " ".join(_text(value).split())


def _number(value):
    """The value as a float, or None for anything that is not a plain number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _round(seconds: float):
    """Whole seconds stay whole, so meta.json reads like the timestamps it feeds."""
    return int(seconds) if float(seconds).is_integer() else seconds


def _date(*values, fallback: str) -> str:
    """The first value that is really a date, as YYYY-MM-DD."""
    for value in values:
        text = _line(value)
        compact = COMPACT_DATE.fullmatch(text)
        if compact:
            return "-".join(compact.groups())
        iso = ISO_DATE.match(text)
        if iso:
            return iso.group(1)
    return fallback


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def chapters(raw) -> list[dict]:
    """Chapters as the schema has them: `start_s`, in order, time first."""
    marks = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        start = _number(item.get("start_time"))
        # A chapter we cannot place in time is not something a deep link could
        # ever point at — drop it rather than store a heading with no moment.
        if start is None:
            continue
        marks.append({"title": _line(item.get("title")), "start_s": _round(max(0.0, start))})
    marks.sort(key=lambda mark: mark["start_s"])
    return marks


def normalize(video_id: str, url: str, info, ingested_at: str | None = None) -> dict:
    """info.json as meta.json: required keys first, optional ones only when real."""
    if not isinstance(info, dict):
        raise BadMeta("the fetcher's info.json is not a JSON object")
    stamp = ingested_at or _now()
    duration = _number(info.get("duration")) or 0.0
    dated = _date(info.get("upload_date"), info.get("release_date"), fallback=stamp[:10])
    document = {
        # The id is ours, not the fetcher's: it names the directory this is
        # written into, and the two disagreeing would break every deep link.
        "id": video_id,
        # The download is already paid for. A source that withheld its title gets
        # the id as one rather than stranding the video with no entry at all.
        "title": _line(info.get("title")) or video_id,
        "channel": _line(info.get("uploader")) or _line(info.get("channel")),
        # Same reasoning, and the schema insists on a date: an undated source is
        # dated the day we ingested it, which the stamp below makes visible.
        "upload_date": dated,
        "duration_s": max(0, round(duration)),
        "url": _text(info.get("webpage_url")) or _text(info.get("original_url")) or url,
    }
    description = _text(info.get("description"))  # multi-line: kept as written
    if description:
        document["description"] = description
    marks = chapters(info.get("chapters"))
    if marks:
        document["chapters"] = marks
    document["ingested_at"] = stamp
    return document


def write(entry: Path, document: dict) -> Path:
    """Atomic swap: an interrupted write leaves the old meta.json intact, never a
    half-parsed one — an entry with unreadable metadata is an entry no verb can
    touch, and the video it describes is the expensive thing to replace."""
    target = entry / META_NAME
    # Dotted temp name: a crashed write stays invisible to anything listing an entry.
    tmp = entry / f".{META_NAME}.{os.getpid()}.tmp"
    try:
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return target
