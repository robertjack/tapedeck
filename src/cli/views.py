"""`list` and `show` (SPEC-cli-001's browsing verbs): read-only renders of
`meta.json`, never re-deriving what counts as downloaded media (LESSON-0003)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import components


def _entries(home: Path):
    library = home / "library"
    if not library.is_dir():
        return
    for entry in sorted(library.iterdir()):
        if not entry.is_dir() or not components.is_video_id(entry.name):
            continue
        meta_path = entry / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict):
            yield entry, meta


def cmd_list(args, home: Path) -> int:
    rows = sorted(
        ({"id": entry.name, **meta} for entry, meta in _entries(home)),
        key=lambda r: (r.get("upload_date") or "", r["id"]),
    )
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r["id"],
                        "upload_date": r.get("upload_date"),
                        "channel": r.get("channel"),
                        "title": r.get("title"),
                    }
                    for r in rows
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    for r in rows:
        date = r.get("upload_date") or "?"
        print(f"{r['id']}  {date:<10}  {r.get('channel', '')} — {r.get('title', '')}")
    return 0


def cmd_show(args, home: Path) -> int:
    vid = args.video_id
    entry = home / "library" / vid
    meta_path = entry / "meta.json"
    if not components.is_video_id(vid) or not meta_path.is_file():
        print(f"error: {vid!r} is not in the library", file=sys.stderr)
        return 2
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: {vid}: meta.json is unreadable — {exc}", file=sys.stderr)
        return 1

    media_present = components.has_media(entry)
    media_files = components.video_files(entry) if media_present else []
    archive_page = home / "archive" / f"{vid}.md"
    transcript_present = (entry / "transcript.json").is_file()

    result = {
        "id": vid,
        "title": meta.get("title"),
        "channel": meta.get("channel"),
        "upload_date": meta.get("upload_date"),
        "duration_s": meta.get("duration_s"),
        "url": meta.get("url"),
        "media": str(media_files[0]) if media_files else None,
        "archive": str(archive_page) if archive_page.is_file() else None,
        "transcript": transcript_present,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"{vid}  {result['title']}")
    print(f"channel:    {result['channel']}")
    print(f"uploaded:   {result['upload_date']}")
    print(f"url:        {result['url']}")
    print(f"media:      {'downloaded' if media_present else 'not downloaded'}")
    print(f"transcript: {'present' if transcript_present else 'missing'}")
    print(f"archive:    {result['archive'] or 'not rendered yet'}")
    return 0
