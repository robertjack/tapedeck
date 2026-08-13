"""The verbs the cli answers itself: what is here (`list`, `show`) and what goes (`rm`).

These read `library/` directly, in the shape the layout contract fixes, because
the library directory *is* the record of what tapedeck has: `rm` removing an
entry is `list` forgetting it, with nothing to keep in step.

Removal (SPEC-cli-002) is the one place the cli destroys anything, and it is
careful about two things. It only ever touches paths named after the id it was
given, so no other video can be caught by it. And it does not reach into
`tapedeck.db` — dropping a video's rows means deleting its archive page and
letting the index, which owns that file, update itself (SPEC-core-001).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import components
from .home import META_NAME, TRANSCRIPT_NAME, VIDEO_ID, entries, entry, media, page


def error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def hms(seconds) -> str:
    """A duration, or nothing at all: a hand-edited meta.json is not worth a crash."""
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return ""
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def load_meta(where: Path) -> dict | None:
    try:
        meta = json.loads((where / META_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def row(video_id: str, meta: dict) -> dict:
    return {
        "id": video_id,
        "upload_date": str(meta.get("upload_date") or ""),
        "channel": str(meta.get("channel") or ""),
        "title": str(meta.get("title") or "(untitled)"),
    }


def catalogue(home: Path) -> list[dict]:
    """Every video in the library, newest first."""
    videos = []
    for video_id in entries(home):
        meta = load_meta(entry(home, video_id))
        if meta is None:
            error(f"{video_id}: no readable {META_NAME} — skipping")
            continue
        videos.append(row(video_id, meta))
    videos.sort(key=lambda video: (video["upload_date"], video["id"]), reverse=True)
    return videos


def show_all(home: Path, as_json: bool) -> int:
    videos = catalogue(home)
    if as_json:
        print(json.dumps(videos, ensure_ascii=False, indent=2))
        return 0
    if not videos:
        print("no videos yet — `tapedeck add <url>` starts one", file=sys.stderr)
        return 0
    for video in videos:
        print(f"{video['id']}  {video['upload_date']}  {video['channel']}  {video['title']}")
    return 0


def show(home: Path, video_id: str, as_json: bool) -> int:
    where = entry(home, video_id)
    if not VIDEO_ID.fullmatch(video_id) or not (where / META_NAME).is_file():
        error(f"{video_id}: not in the library")
        return 2
    meta = load_meta(where)
    if meta is None:
        error(f"{video_id}: {META_NAME} is unreadable")
        return 1
    rendered = page(home, video_id)
    files = media(where)
    transcript = where / TRANSCRIPT_NAME
    if as_json:
        print(
            json.dumps(
                {
                    **meta,
                    "archive": str(rendered) if rendered.is_file() else None,
                    "media": str(files[0]) if files else None,
                    "transcript": str(transcript) if transcript.is_file() else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    listed = row(video_id, meta)
    facts = " · ".join(
        part
        for part in (listed["channel"], listed["upload_date"], hms(meta.get("duration_s")))
        if part
    )
    print(f"{listed['title']}\n{facts}\n{str(meta.get('url') or '')}\n")
    print(f"id          {video_id}")
    print(f"archive     {rendered if rendered.is_file() else '— run `tapedeck add` to re-render'}")
    print(f"video       {files[0].name if files else '— removed; `tapedeck add` re-fetches it'}")
    print(f"transcript  {transcript if transcript.is_file() else '— not transcribed yet'}")
    return 0


def remove(home: Path, video_id: str, media_only: bool) -> int:
    where = entry(home, video_id)
    rendered = page(home, video_id)
    if not VIDEO_ID.fullmatch(video_id) or not (where.is_dir() or rendered.is_file()):
        error(f"{video_id}: not in the library — nothing to remove")
        return 2
    if media_only:
        return drop_media(where, video_id)

    # Page first, then the index update it makes true, then the entry: interrupted
    # anywhere, the id still resolves and a second `rm` finishes the job.
    rendered.unlink(missing_ok=True)
    indexed = components.run("index", ["update", video_id], home, capture=True).returncode
    shutil.rmtree(where, ignore_errors=True)
    if where.exists():
        error(f"{video_id}: {where} could not be removed")
        return 1
    if indexed != 0:
        error(f"{video_id}: files removed, but the index still has it — run `tapedeck reindex`")
        return 1
    print(f"{video_id}: removed")
    return 0


def drop_media(where: Path, video_id: str) -> int:
    """Reclaim the disk, keep the knowledge: the transcript, the archive page and
    the index rows outlive the file they came from — at the price of never
    re-deriving them without downloading the video again (SPEC-cli-002)."""
    files = media(where)
    for path in files:
        path.unlink()
    if not files:
        print(f"{video_id}: no video file to remove", file=sys.stderr)
    print(f"{video_id}: media removed — transcript, archive page and index entries kept")
    return 0
