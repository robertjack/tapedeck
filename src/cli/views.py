"""What `list` and `show` put on stdout, in both dialects.

Two read-only views over the library, and the only place the cli formats facts of
its own. Both put the id first, because every other verb takes one. `--json` is
the same facts structurally: the entry's `meta.json` as ingest wrote it, plus
where the derived files are — a reshaped copy would be a second metadata format
for readers to learn.

`show` reports presence, never guesses: a video the library does not have is said
to be missing rather than named hopefully, because that answer is what tells the
user `add` will fetch it again. What counts as having it is ingest's rule, so a
`video.part` left by an interrupted download reads here exactly as it reads there
— not the video (LESSON-0003).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from archive.render import hms

from . import Failure, library
from .library import Entry

UNKNOWN = "unknown"


def _row(entry: Entry, meta: dict) -> dict:
    return {
        "id": entry.video_id,
        "upload_date": str(meta.get("upload_date") or UNKNOWN),
        "channel": str(meta.get("channel") or ""),
        "title": str(meta.get("title") or ""),
        "duration_s": meta.get("duration_s"),
    }


def listing(home: Path, as_json: bool) -> int:
    rows = []
    for entry in library.entries(home):
        meta = entry.meta()
        if not meta:
            print(f"{entry.video_id}: no readable meta.json — not listed", file=sys.stderr)
            continue
        rows.append(_row(entry, meta))
    rows.sort(key=lambda row: (row["upload_date"], row["id"]))
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    # One line per video, columns aligned to this library rather than to a guess
    # about channel-name lengths.
    width = max((len(row["channel"]) for row in rows), default=0)
    for row in rows:
        print(f"{row['id']}  {row['upload_date']}  {row['channel']:<{width}}  {row['title']}")
    return 0


def _duration(meta: dict) -> str:
    """`duration_s: 0` is a duration the source withheld, not a zero-second video
    (contracts/ask-citations.md) — so it is reported as the unknown it is."""
    seconds = meta.get("duration_s")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
        return UNKNOWN
    return hms(seconds)


def show(home: Path, video_id: str, as_json: bool) -> int:
    entry = Entry(home, video_id)
    if not library.is_video_id(video_id) or not entry.known():
        raise Failure(
            f"no video {video_id!r} in the library — `tapedeck list` shows what is",
            code=2,
        )
    meta = entry.meta()
    media = entry.media()
    derived = {
        "media": str(media) if media else None,
        "transcript": _path(entry.transcript_path),
        "model": entry.model(),
        "archive": _path(entry.page),
    }
    if as_json:
        print(json.dumps({**meta, **derived}, indent=2, ensure_ascii=False))
        return 0
    print(f"{video_id}  {meta.get('title', '')}".rstrip())
    for label, value in (
        ("channel", meta.get("channel") or UNKNOWN),
        ("uploaded", meta.get("upload_date") or UNKNOWN),
        ("duration", _duration(meta)),
        ("url", meta.get("url") or UNKNOWN),
    ):
        print(f"  {label:<10}  {value}")
    print(f"  {'video':<10}  {derived['media'] or _gone('add ' + video_id + ' --force')}")
    transcript = derived["transcript"]
    if transcript and derived["model"]:
        transcript = f"{transcript}  ({derived['model']})"
    print(f"  {'transcript':<10}  {transcript or _gone('retranscribe')}")
    print(f"  {'archive':<10}  {derived['archive'] or _gone('add ' + video_id)}")
    return 0


def _path(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def _gone(verb: str) -> str:
    return f"missing — `tapedeck {verb}` derives it again"
