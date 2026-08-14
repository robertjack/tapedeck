"""`list` and `show`: what the library holds, for a person and for a program.

Read-only, and both shapes carry the same facts — `--json` is the same answer
with the formatting taken out (SPEC-cli-001), never a different query.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from archive import hms  # the timestamp format is archive's (LESSON-0003)

from . import FAILURE, USAGE, Failure, library

ROW_KEYS = ("id", "upload_date", "channel", "title")


def _row(document: dict) -> dict:
    return {key: document.get(key) or "" for key in ROW_KEYS}


def listing(home: Path, as_json: bool) -> int:
    """One line per video: id, date, channel, title. Newest first."""
    rows, unreadable = [], []
    for video_id in library.ids(home):
        document = library.meta(home, video_id)
        if document is None:
            # An entry mid-fetch, or one whose metadata did not survive. It is
            # not a video anyone can browse yet, so it is not in the listing —
            # but silence would make it look as though it were gone.
            unreadable.append(video_id)
            continue
        rows.append(_row({**document, "id": video_id}))
    rows.sort(key=lambda row: (row["upload_date"], row["title"]), reverse=True)

    for video_id in unreadable:
        print(f"{video_id}: no readable meta.json — not listed", file=sys.stderr)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        print(f"{row['id']}  {row['upload_date']:<10}  {row['channel']}  {row['title']}")
    return 0


def show(home: Path, video_id: str, as_json: bool) -> int:
    """One video: its metadata, and where each of its files is — or is not."""
    if not library.is_video_id(video_id):
        raise Failure(f"{video_id!r} is not a video id", code=USAGE)
    if not library.entry(home, video_id).is_dir():
        raise Failure(
            f"no video {video_id} in the library — `tapedeck list` shows what is",
            code=USAGE,
        )
    document = library.meta(home, video_id)
    if document is None:
        raise Failure(
            f"{video_id}: meta.json is missing or unreadable — "
            f"`tapedeck add {video_id}` re-fetches it",
            code=FAILURE,
        )

    # Media is present exactly when ingest says it is: a half-finished download
    # beside the entry is not a video here either, which is also what tells the
    # reader that `add` would fetch it again.
    media = library.media(home, video_id)
    transcript = library.transcript(home, video_id)
    page = library.page(home, video_id)
    if as_json:
        print(
            json.dumps(
                {
                    **document,
                    "id": video_id,
                    "media": str(media) if media else None,
                    "transcript": str(transcript) if transcript else None,
                    "archive": str(page) if page.is_file() else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print("\n".join(_human(video_id, document, media, transcript, page)))
    return 0


def _human(video_id: str, document: dict, media, transcript, page) -> list[str]:
    duration = document.get("duration_s")
    lines = [f"{video_id}  {document.get('title', '')}"]
    for label, value in (
        ("channel", document.get("channel", "")),
        ("uploaded", document.get("upload_date", "")),
        ("duration", hms(duration) if isinstance(duration, (int, float)) else "unknown"),
        ("url", document.get("url", "")),
    ):
        lines.append(f"  {label:<10} {value}")
    lines.append(f"  {'archive':<10} {page if page.is_file() else 'not rendered yet'}")
    lines.append(
        f"  {'video':<10} "
        + (str(media) if media else f"gone — `tapedeck add {video_id}` fetches it again")
    )
    lines.append(
        f"  {'transcript':<10} " + (str(transcript) if transcript else "none yet")
    )
    chapters = document.get("chapters") or []
    if chapters:
        lines.append(f"  {'chapters':<10} {len(chapters)}")
    return lines
