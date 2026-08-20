"""The fetcher's info json, normalized into `library/<id>/meta.json`.

What a downloader reports is its own business: yt-dlp writes `uploader` and
`upload_date: "20260115"` and chapters keyed `start_time`. What the rest of
tapedeck reads is `system/contracts/meta.schema.json` — one flat shape, dates in
ISO, durations in whole seconds, chapters keyed `start_s`. This module is the
only place that translation happens, and it is deliberately forgiving on the way
in and strict on the way out: a field the fetcher omitted becomes a sane default,
a field it spelled its own way is looked for under every spelling, and nothing
the schema does not name is written.

A local file (SPEC-ingest-005) is normalized through the exact same function: it
hands in a yt-dlp-info-json-shaped dict built from what the file can honestly say
about itself (`local.info`), so this module never has to know where a video
came from.

The one thing that cannot be defaulted is a title, because a library of
"Untitled" is not a library. No title is a failed ingest.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

META_NAME = "meta.json"
COMPACT_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
ISO_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")  # a full timestamp keeps its date


class BadMeta(ValueError):
    """The fetcher's metadata cannot become a schema-valid meta.json."""


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _line(value) -> str:
    """A one-line field: newlines in a title would break every line-oriented read."""
    return " ".join(_text(value).split())


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if isinstance(value, str) and value.strip() else None
    except ValueError:
        return None


def _seconds(value) -> int:
    """Whole seconds, never negative. A fetcher that reported no duration leaves 0
    — readers treat that as unknown rather than as a claim about the video."""
    number = _number(value)
    return max(0, round(number)) if number is not None else 0


def _date(*values, fallback: str) -> str:
    """`20260115` and `2026-01-15T09:00:00Z` are both 2026-01-15."""
    for value in values:
        text = _text(value)
        compact = COMPACT_DATE.match(text)
        if compact:
            return "-".join(compact.groups())
        iso = ISO_DATE.match(text)
        if iso:
            return iso.group(1)
    return fallback


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def chapters(raw) -> list[dict]:
    """The source's chapters when it has them, in the schema's key. A chapter with
    no usable start is dropped rather than guessed at — a wrong deep link is worse
    than a missing section."""
    marks = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        start = _number(item.get("start_time", item.get("start_s")))
        if start is None or start < 0:
            continue
        marks.append({"title": _line(item.get("title")), "start_s": start})
    return marks


def normalize(video_id: str, url: str, info, ingested_at: str | None = None) -> dict:
    """A schema-valid meta document, or BadMeta. Keys the schema does not name are
    dropped: `additionalProperties: false` means an unknown key fails validation
    everywhere downstream, not here."""
    if not isinstance(info, dict):
        raise BadMeta("the fetcher's metadata is not a JSON object")
    title = _line(info.get("title") or info.get("fulltitle"))
    if not title:
        raise BadMeta(f"the fetcher's metadata carries no title for {video_id}")
    document = {
        "id": video_id,
        "title": title,
        "channel": _line(info.get("channel") or info.get("uploader")),
        "upload_date": _date(
            info.get("upload_date"), info.get("release_date"), fallback=_today()
        ),
        "duration_s": _seconds(info.get("duration")),
        "url": _line(info.get("webpage_url") or info.get("original_url")) or url,
        "ingested_at": ingested_at or _now(),
    }
    description = _text(info.get("description"))
    if description:
        document["description"] = description
    marks = chapters(info.get("chapters"))
    if marks:
        document["chapters"] = marks
    return document


def write(entry: Path, document: dict) -> Path:
    """meta.json, replaced in one step. A reader either sees the whole old file or
    the whole new one — never a half-written entry that reads as complete."""
    path = entry / META_NAME
    staged = entry / f".{META_NAME}.new"
    staged.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(staged, path)
    return path
