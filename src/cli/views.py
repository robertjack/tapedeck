"""The verbs that read the library, and the one that unmakes part of it.

`list` and `show` report what is here; `rm` removes it. All three ask the same
questions the pipeline asks, of the same owners — an id is well-formed by
ingest's grammar, an entry holds a video by ingest's rule — so `show` and a sweep
can never disagree about whether a video is present. That matters most where it
is least visible: after `rm --media-only`, `show` says the video is gone while
the knowledge stays, which is exactly what `add` would do about it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from archive import hms

from . import library
from .components import Failed, Usage, quietly

CHANNEL_WIDTH = 24
GONE = "absent — `tapedeck add {id}` fetches it again"


def list_videos(home: Path, as_json: bool) -> int:
    """One line per video: id, date, channel, title. Newest first."""
    rows = []
    for video_id in library.entries(home):
        meta = library.meta(home, video_id)
        if meta is None:
            print(f"{video_id}: no readable meta.json — skipped", file=sys.stderr)
            continue
        rows.append(
            {
                "id": video_id,
                "upload_date": str(meta.get("upload_date") or ""),
                "channel": str(meta.get("channel") or ""),
                "title": str(meta.get("title") or ""),
            }
        )
    rows.sort(key=lambda row: (row["upload_date"], row["id"]), reverse=True)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    width = min(CHANNEL_WIDTH, max((len(row["channel"]) for row in rows), default=0))
    for row in rows:
        channel = row["channel"].ljust(width)
        print(f"{row['id']}  {row['upload_date']}  {channel}  {row['title']}")
    return 0


def show(home: Path, video_id: str, as_json: bool) -> int:
    """Everything the library knows about one video, and where it all is."""
    if not library.is_video_id(video_id):
        raise Usage(f"{video_id!r} is not a video id")
    if not library.entry_dir(home, video_id).is_dir():
        raise Usage(f"{video_id}: not in the library — `tapedeck list` shows what is")
    meta = library.meta(home, video_id)
    if meta is None:
        raise Failed(f"{video_id}: meta.json is missing or unreadable")

    media = library.media(home, video_id)
    page = library.page_path(home, video_id)
    transcript = library.transcript(home, video_id)
    document = {
        "id": video_id,
        "title": meta.get("title"),
        "channel": meta.get("channel"),
        "upload_date": meta.get("upload_date"),
        "duration_s": meta.get("duration_s"),
        "url": meta.get("url"),
        "media": str(media) if media else None,
        "transcript": _transcript_summary(transcript),
        "archive": str(page) if page.is_file() else None,
    }
    if as_json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    _print_show(document, meta)
    return 0


def _transcript_summary(transcript: dict | None) -> dict | None:
    if transcript is None:
        return None
    segments = transcript.get("segments")
    return {
        "model": transcript.get("model"),
        "segments": len(segments) if isinstance(segments, list) else 0,
    }


def _print_show(document: dict, meta: dict) -> None:
    duration = document["duration_s"]
    stamp = hms(duration) if isinstance(duration, (int, float)) else "unknown length"
    print(f"{document['id']}  {document['title']}")
    print(f"{document['channel']} · {document['upload_date']} · {stamp}")
    print(document["url"])
    print()
    # The video's absence is reported, never the name of what sits in its place:
    # a `video.part` is a fetch in flight, and printing it would read as a video.
    print(f"video       {document['media'] or GONE.format(id=document['id'])}")
    transcript = document["transcript"]
    if transcript:
        print(f"transcript  {transcript['segments']} segments ({transcript['model']})")
    else:
        print(f"transcript  none — `tapedeck add {document['id']}` derives it")
    print(f"archive     {document['archive'] or 'not rendered yet'}")
    chapters = meta.get("chapters")
    if isinstance(chapters, list) and chapters:
        print(f"chapters    {len(chapters)}")


def remove(home: Path, video_id: str, media_only: bool) -> int:
    """`rm` — the video everywhere, or just the bytes on disk (SPEC-cli-002).

    Only ever this video's paths: one entry directory, one archive page, one
    video's rows. The index is told about the removal the same way it is told
    about a render — `index update <id>`, which finds no page and drops exactly
    those rows, leaving every other video's untouched.
    """
    if not library.is_video_id(video_id):
        raise Usage(f"{video_id!r} is not a video id")
    entry = library.entry_dir(home, video_id)
    page = library.page_path(home, video_id)
    if not entry.is_dir() and not page.is_file():
        raise Usage(f"{video_id}: not in the library — nothing to remove")

    if media_only:
        return _reclaim(home, video_id, entry)
    shutil.rmtree(entry, ignore_errors=True)
    page.unlink(missing_ok=True)
    if quietly(home, "index", ["update", video_id]):
        raise Failed(f"{video_id}: removed from disk, but the index still lists it")
    print(f"{video_id}: removed — library entry, archive page and index rows")
    return 0


def _reclaim(home: Path, video_id: str, entry: Path) -> int:
    """Disk back, knowledge kept. What goes is the video by ingest's rule and
    nothing else: metadata, transcript, archive page and index rows all stay, and
    the video is the one thing here that can never be re-derived without the
    network — which is the trade this flag names."""
    if not entry.is_dir():
        raise Usage(f"{video_id}: no library entry — there is no media to reclaim")
    removed = 0
    for path in library.media_files(home, video_id):
        path.unlink()
        removed += 1
    if not removed:
        print(f"{video_id}: no video file here — nothing to reclaim", file=sys.stderr)
        return 0
    print(f"{video_id}: removed {removed} video file(s); transcript, page and index kept")
    return 0
