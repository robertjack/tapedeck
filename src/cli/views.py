"""The verbs that read the library, and the one that unmakes part of it.

`list` and `show` answer from `library/<id>/meta.json` — the only thing the cli
reads out of another component's files — and both are read-only. `rm` is the
opposite: it is the one verb whose whole purpose is to remove, so it says exactly
what it removed and touches nothing else (SPEC-cli-002).

The two questions these verbs ask about an entry belong to ingest, and are asked
of it: whether a name is a video id, and whether the media is really there.
`show` reporting `video.part` as the video would tell a user their download is
fine when what they have is half of one — the same wrong answer that would make
`add` skip re-fetching it (LESSON-0003).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import ingest
from archive import hms

from . import Failure, Usage, components
from .home import LIBRARY
from .pipeline import META_NAME, TRANSCRIPT_NAME, entry_of, label, page_of

UNKNOWN = "{0!r} is not a video in the library — `tapedeck list` shows what is"


def entries(home: Path) -> list[Path]:
    """Every library entry, by ingest's grammar. A user's own directory under
    `library/` is not one, and is left out rather than reported as a broken video."""
    library = home / LIBRARY
    found = library.iterdir() if library.is_dir() else []
    return sorted(p for p in found if p.is_dir() and ingest.VIDEO_ID.fullmatch(p.name))


def read_meta(entry: Path) -> dict | None:
    try:
        document = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def known(home: Path, video_id: str) -> Path:
    """The entry for an id, or a usage error naming what was asked for."""
    entry = entry_of(home, video_id)
    if not ingest.VIDEO_ID.fullmatch(video_id or "") or not entry.is_dir():
        raise Usage(UNKNOWN.format(video_id))
    return entry


def listing(home: Path, as_json: bool) -> int:
    """One line per video: id, date, channel, title. Newest first."""
    rows = []
    for entry in entries(home):
        meta = read_meta(entry)
        if meta is None:
            continue  # an entry mid-fetch has no metadata yet; it is not a video
        rows.append(
            {
                "id": entry.name,
                "upload_date": str(meta.get("upload_date") or ""),
                "channel": str(meta.get("channel") or ""),
                "title": str(meta.get("title") or ""),
                "duration_s": meta.get("duration_s"),
            }
        )
    rows.sort(key=lambda row: (row["upload_date"], row["id"]), reverse=True)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    width = max((len(row["channel"]) for row in rows), default=0)
    for row in rows:
        date = row["upload_date"] or "----------"
        print(f"{row['id']}  {date}  {row['channel']:<{width}}  {row['title']}")
    return 0


def show(home: Path, video_id: str, as_json: bool) -> int:
    """Everything the library knows about one video, and where to open it."""
    entry = known(home, video_id)
    meta = read_meta(entry) or {}
    media = ingest.videos(entry)
    page = page_of(home, video_id)
    transcript = entry / TRANSCRIPT_NAME
    document = {
        **meta,
        "id": video_id,
        "media": str(media[0]) if media else None,
        "transcript": str(transcript) if transcript.is_file() else None,
        "model": label(entry),
        "archive": str(page) if page.is_file() else None,
    }
    if as_json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0

    duration = document.get("duration_s")
    print(f"{video_id}  {document.get('title') or '(no title)'}")
    for field, value in (
        ("channel", document.get("channel")),
        ("date", document.get("upload_date")),
        ("duration", hms(duration) if isinstance(duration, (int, float)) else None),
        ("url", document.get("url")),
        ("media", document["media"] or f"gone — `tapedeck add {video_id} --force` refetches it"),
        ("transcript", document["model"] or "none — `tapedeck retranscribe` derives it"),
        ("archive", document["archive"] or "none — `tapedeck add <id>` re-renders it"),
    ):
        print(f"  {field:<11} {value or '(unknown)'}")
    return 0


def remove(home: Path, video_id: str, media_only: bool) -> int:
    """Forget a video, or reclaim just its disk (SPEC-cli-002)."""
    entry = known(home, video_id)
    if media_only:
        # The knowledge stays: metadata, transcript, archive page and index rows
        # all keep working. The cost is that this video can never be
        # re-transcribed without downloading it again.
        for path in ingest.videos(entry):
            path.unlink()
        print(f"{video_id}: media deleted; transcript, archive page and index kept")
        return 0
    shutil.rmtree(entry)
    page_of(home, video_id).unlink(missing_ok=True)
    # The page is gone, so index update is what drops the rows — the index owns
    # its own database, and it derives from archive pages alone.
    code = components.stage("index", ["update", video_id], home)
    if code:
        raise Failure(
            f"{video_id}: removed from the library, but the index still lists it "
            f"(index exited {code}) — `tapedeck reindex` settles it"
        )
    print(f"{video_id}: removed from the library, the archive and the index")
    return 0


def search(home: Path, query, limit, as_json: bool) -> int:
    args = ["search", *query]
    if limit is not None:
        args += ["-k", str(limit)]
    return components.passthrough("index", args + (["--json"] if as_json else []), home)


def ask(home: Path, question, limit, fast: bool, video: str | None) -> int:
    args = ["run", " ".join(question)]
    if limit is not None:
        args += ["-k", str(limit)]
    if fast:
        args.append("--fast")
    if video is not None:
        args += ["--video", video]
    return components.passthrough("ask", args, home)


def reindex(home: Path) -> int:
    """The index rebuilt from archive pages alone — the component's verb, whole."""
    return components.passthrough("index", ["reindex"], home)
