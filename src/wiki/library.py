"""The library as the wiki reads it: which videos exist, which can be filed, and
in what order a sweep should meet them.

Every rule here belongs to another component and is consumed rather than
re-derived (LESSON-0003). Whether a name is a video id and whether the media is
really there are ingest's — `ingest.VIDEO_ID` and `ingest.has_video`, imported,
not copied. Whether a name that is *not* a video id is one of ingest's own
download staging directories is ingest's too — `ingest.staging(name)`
(SPEC-ingest-003) — asked rather than pattern-matched, because a directory named
`.fetching-<id>-<random>` is a download in progress or interrupted, and it is
tapedeck's own (SPEC-wiki-010): calling it foreign or a stranger is how a live
`yt-dlp` gets recommended for deletion by a reader following the note. Whether
there is anything to file *from* is archive's: the maintainer reads
`archive/<id>.md`, so a video without one has nothing to be read.

Selection is the retranscribe sweep's discipline (SPEC-cli-004) applied one layer
up, quoted deliberately rather than reinvented: a real library keeps entries no
sweep can ever satisfy — a directory of the user's own, a download in flight, an
entry whose video `rm --media-only` reclaimed, one archive has not rendered yet —
and a sweep that fails on them can never converge. Each gets a note on stderr and
is left alone.

The order is `upload_date` ascending, ties broken by id, and it is not a detail.
The wiki is path-dependent state: a maintainer writes against the wiki as it
already stands, so filing in upload order makes the wiki accumulate in the order
the material appeared, and the tiebreak means the same library filed twice
produces the same sequence rather than whatever order the filesystem returned.
"""

from __future__ import annotations

import json
from pathlib import Path

import ingest

LIBRARY = "library"
ARCHIVE = "archive"
META = "meta.json"


def entry(home: Path, video_id: str) -> Path:
    return home / LIBRARY / video_id


def holds(home: Path, video_id: str) -> bool:
    """Is this video in the library? The entry, not the media — a video reclaimed
    by `rm --media-only` was explicitly kept as knowledge."""
    return entry(home, video_id).is_dir()


def archive_page(home: Path, video_id: str) -> Path:
    return home / ARCHIVE / f"{video_id}.md"


def upload_date(home: Path, video_id: str) -> str:
    """When the material appeared, from the video's own metadata. An entry whose
    meta.json cannot be read sorts first and is filed all the same: the sweep's
    order is a choice about the artifact, not a precondition for making it."""
    try:
        meta = json.loads((entry(home, video_id) / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return meta.get("upload_date", "") if isinstance(meta, dict) else ""


def eligible(home: Path, note=None) -> list[str]:
    """Every video a filing could actually be attempted on, in sweep order.

    `note` is called with a sentence for each entry that is passed over; a
    diagnosis that only reads passes nothing, so the same walk serves `lint`.
    """
    root = home / LIBRARY
    found = []
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        name = path.name
        if not path.is_dir():
            continue
        if not ingest.VIDEO_ID.fullmatch(name):
            fetching = ingest.staging(name)
            if fetching is not None:
                _say(
                    note,
                    f"{name}: a tapedeck download in progress for {fetching} — "
                    f"left alone, skipped",
                )
            else:
                _say(note, f"{name}: not a video id — skipped, it is not tapedeck's")
        elif not ingest.has_video(path):
            _say(
                note,
                f"{name}: no video here — skipped; the entry was reclaimed by "
                f"`tapedeck rm --media-only`, and `tapedeck add {name}` brings it back",
            )
        elif not archive_page(home, name).is_file():
            _say(
                note,
                f"{name}: no archive page — skipped; there is nothing to read it "
                f"from until `tapedeck add {name}` renders one",
            )
        else:
            found.append(name)
    return sorted(found, key=lambda vid: (upload_date(home, vid), vid))


def _say(note, message: str) -> None:
    if note is not None:
        note(message)
