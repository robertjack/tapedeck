"""What a local file can honestly say about itself (SPEC-ingest-005).

A video does not have to come from YouTube: a lecture capture, a meeting
recording, footage someone sent you is a video too. Its metadata is built from
the file alone, never invented — `title` is the filename without its extension,
`upload_date` is the file's own modification date, `channel` is empty because a
local file has no publisher, and `url` is the file's own `file://` address,
which is what lets the layout contract's deep-link rule address a moment in it
with no second rule.

`duration_s` is read from the media with `ffprobe` — not a new dependency, it
ships with the ffmpeg the pipeline already requires and `doctor` already checks
— because every citation this system verifies is checked against that number: a
guessed duration would launder itself into evidence, so an add whose duration
cannot be read fails instead of recording one.

The library never copies a local file: `install_link` places a symlink where a
download would place a video, named the same way (`video.<ext>`) so every other
reader of an entry — `fetch.videos`, `fetch.has_video` — needs no second rule to
recognize it. That is also what makes the degradation the spec promises free:
delete the original and the symlink dangles, `Path.is_file()` on it reads
False, and the entry is exactly the media-only state `rm --media-only` already
leaves.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

FFPROBE = ("ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1")
PROBE_TIMEOUT = 30


class MediaError(RuntimeError):
    """The file exists but its duration cannot be read from it."""


def title(path: Path) -> str:
    return path.stem


def upload_date(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return stamp.strftime("%Y-%m-%d")


def file_url(path: Path) -> str:
    return path.as_uri()


def duration_s(path: Path) -> int:
    """Whole seconds read from the media itself, or MediaError — never a guess,
    because a citation-bearing number that is wrong is worse than an add that
    fails."""
    try:
        result = subprocess.run(
            [*FFPROBE, str(path)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"ffprobe could not read {path}: {exc}") from exc
    if result.returncode != 0:
        raise MediaError(f"ffprobe could not read {path}: {result.stderr.strip()}")
    try:
        return max(0, round(float(result.stdout.strip())))
    except ValueError as exc:
        raise MediaError(f"ffprobe reported no duration for {path}") from exc


def info(path: Path) -> dict:
    """The yt-dlp-info-json-shaped document `meta.normalize` already knows how to
    read, built entirely from what this file can honestly say about itself."""
    return {
        "title": title(path),
        "channel": "",
        "upload_date": upload_date(path),
        "duration": duration_s(path),
        "webpage_url": file_url(path),
    }


def install_link(dest: Path, source: Path) -> Path:
    """A symlink at `dest/video<ext>` pointing at `source`, so the entry
    references the file rather than doubling its disk cost. Named like a
    fetcher's output so `fetch.videos()` needs no second rule to see it."""
    link = dest / f"video{source.suffix}"
    os.symlink(source, link)
    return link
