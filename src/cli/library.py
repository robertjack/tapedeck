"""The verbs the cli answers itself: what is here (`list`, `show`) and what goes (`rm`).

These read `library/` directly, in the shape the layout contract fixes, because
the library directory *is* the record of what tapedeck has: `rm` removing an
entry is `list` forgetting it, with nothing to keep in step.

Removal (SPEC-cli-002) is the one place the cli destroys anything, and it is
careful about two things. It only ever touches paths named after the id it was
given, so no other video can be caught by it. And it does not reach into
`tapedeck.db` — dropping a video's rows means deleting its archive page and
letting the index, which owns that file, update itself from the archive that no
longer mentions it (SPEC-core-001).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import components, home as home_mod

META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.json"
MEDIA_STEM = "video"


def error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def hms(seconds) -> str:
    """A duration, or nothing at all: a hand-edited meta.json is not worth a crash."""
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return ""
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def is_media(path: Path) -> bool:
    """`library/<id>/video.<ext>` — the download itself, and nothing derived from it."""
    return path.is_file() and path.stem == MEDIA_STEM and path.suffix.lower() != ".json"


def media_files(entry: Path) -> list[Path]:
    return sorted(path for path in entry.iterdir() if is_media(path)) if entry.is_dir() else []


def load_meta(entry: Path) -> dict | None:
    try:
        meta = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
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
    library = home / home_mod.LIBRARY
    videos = []
    for entry in sorted(library.iterdir()) if library.is_dir() else []:
        # A dotted directory is a fetch in flight or a crashed one — not a video yet.
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        meta = load_meta(entry)
        if meta is None:
            error(f"{entry.name}: no readable {META_NAME} — skipping")
            continue
        videos.append(row(entry.name, meta))
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
    entry = home_mod.entry(home, video_id)
    if not home_mod.VIDEO_ID.fullmatch(video_id) or not (entry / META_NAME).is_file():
        error(f"{video_id}: not in the library")
        return 2
    meta = load_meta(entry)
    if meta is None:
        error(f"{video_id}: {META_NAME} is unreadable")
        return 1
    page = home_mod.page(home, video_id)
    media = media_files(entry)
    transcript = entry / TRANSCRIPT_NAME
    if as_json:
        print(
            json.dumps(
                {
                    **meta,
                    "archive": str(page) if page.is_file() else None,
                    "media": str(media[0]) if media else None,
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
    print(f"archive     {page if page.is_file() else '— run `tapedeck add` to re-render'}")
    print(f"video       {media[0].name if media else '— removed; `tapedeck add` re-fetches it'}")
    print(f"transcript  {transcript if transcript.is_file() else '— not transcribed yet'}")
    return 0


def remove(home: Path, video_id: str, media_only: bool) -> int:
    entry = home_mod.entry(home, video_id)
    page = home_mod.page(home, video_id)
    if not home_mod.VIDEO_ID.fullmatch(video_id) or not (entry.is_dir() or page.is_file()):
        error(f"{video_id}: not in the library — nothing to remove")
        return 2
    if media_only:
        return drop_media(entry, video_id)

    # Page first, then the index update it makes true, then the entry: interrupted
    # anywhere, the id still resolves and a second `rm` finishes the job.
    page.unlink(missing_ok=True)
    indexed = components.run("index", ["update", video_id], home, capture=True).returncode
    shutil.rmtree(entry, ignore_errors=True)
    if entry.exists():
        error(f"{video_id}: {entry} could not be removed")
        return 1
    if indexed != 0:
        error(f"{video_id}: files removed, but the index still has it — run `tapedeck reindex`")
        return 1
    print(f"{video_id}: removed")
    return 0


def drop_media(entry: Path, video_id: str) -> int:
    """Reclaim the disk, keep the knowledge: the transcript, the archive page and the
    index rows all outlive the file they came from — at the price of never being able
    to re-derive them without downloading the video again (SPEC-cli-002)."""
    files = media_files(entry)
    for path in files:
        path.unlink()
    if not files:
        print(f"{video_id}: no video file to remove", file=sys.stderr)
    print(f"{video_id}: media removed — transcript, archive page and index entries kept")
    return 0
