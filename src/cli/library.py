"""Reading the library — what `list` and `show` answer from.

cli writes nothing under library/ or archive/; those belong to ingest,
transcribe and archive. This is a reader of meta.json and of what happens to be
beside it, which is why `show` can tell you a video is here but not yet
transcribed. An entry with unreadable metadata is skipped from a listing with a
word on stderr rather than being fatal: one damaged entry must not make the
whole library unlistable.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import Failure

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.json"


def hms(seconds) -> str:
    s = int(seconds or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def entry_dir(home: Path, video_id: str) -> Path:
    return home / "library" / video_id


def archive_page(home: Path, video_id: str) -> Path:
    return home / "archive" / f"{video_id}.md"


def read_meta(home: Path, video_id: str) -> dict:
    path = entry_dir(home, video_id) / META_NAME
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Failure(f"{video_id}: {META_NAME} is unreadable — {exc}") from exc
    if not isinstance(meta, dict):
        raise Failure(f"{video_id}: {META_NAME} is not a JSON object")
    return meta


def record(home: Path, video_id: str, meta: dict) -> dict:
    """One video as tapedeck knows it: what ingest recorded, plus how far along
    the derivation chain this entry has actually got."""
    entry = entry_dir(home, video_id)
    page = archive_page(home, video_id)
    transcript = entry / TRANSCRIPT_NAME
    return {
        "id": video_id,
        "title": str(meta.get("title") or video_id),
        "channel": str(meta.get("channel") or ""),
        "upload_date": str(meta.get("upload_date") or ""),
        "duration_s": meta.get("duration_s"),
        "url": str(meta.get("url") or ""),
        "library": str(entry),
        "transcript": str(transcript) if transcript.is_file() else None,
        "archive": str(page) if page.is_file() else None,
    }


def records(home: Path) -> list[dict]:
    """Every video in the library, newest upload first. Directories that are not
    entries — a fetch still staging under a dotted name — are simply not videos."""
    library = home / "library"
    found = []
    for path in sorted(p for p in library.iterdir() if p.is_dir()) if library.is_dir() else []:
        if not VIDEO_ID.fullmatch(path.name) or not (path / META_NAME).is_file():
            continue
        try:
            found.append(record(home, path.name, read_meta(home, path.name)))
        except Failure as exc:
            print(f"warning: {exc}", file=sys.stderr)
    return sorted(found, key=lambda r: (r["upload_date"], r["id"]), reverse=True)


def one(home: Path, video_id: str) -> dict:
    """The record for a single video, or a validation error naming what is wrong."""
    if not VIDEO_ID.fullmatch(video_id):
        raise Failure(f"{video_id!r} is not an 11-character video id", code=2)
    if not (entry_dir(home, video_id) / META_NAME).is_file():
        raise Failure(f"{video_id}: not in the library ({home / 'library'})", code=2)
    return record(home, video_id, read_meta(home, video_id))


def listing(found: list[dict]) -> str:
    """One line per video: id, date, channel, title — aligned so the titles line up."""
    width = max((len(r["channel"]) for r in found), default=0)
    return "\n".join(
        f"{r['id']}  {r['upload_date'] or '----------'}  "
        f"{r['channel']:<{width}}  {r['title']}".rstrip()
        for r in found
    )


def detail(found: dict) -> str:
    """Everything about one video, ending in where to read it."""
    fields = [
        ("id", found["id"]),
        ("channel", found["channel"]),
        ("uploaded", found["upload_date"]),
        ("duration", hms(found["duration_s"]) if found["duration_s"] is not None else ""),
        ("url", found["url"]),
        ("library", found["library"]),
        ("transcript", found["transcript"] or "not transcribed yet"),
        ("archive", found["archive"] or "not rendered yet — run `tapedeck add <id>`"),
    ]
    lines = [found["title"]]
    lines += [f"  {label:<10}  {value}" for label, value in fields if value]
    return "\n".join(lines)


def ingested_id(stdout: str) -> str:
    """The id ingest just wrote, read back from the entry path it printed.

    ingest owns what a YouTube address means (SPEC-ingest-001); parsing the URL
    again here would be a second answer to that question, free to diverge from
    the first and to start a duplicate entry when it did.
    """
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    name = Path(lines[-1]).name if lines else ""
    if not VIDEO_ID.fullmatch(name):
        raise Failure(f"ingest named no library entry to derive from: {stdout.strip()!r}")
    return name
