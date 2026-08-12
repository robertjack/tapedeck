"""The fetcher seam (SPEC-core-004) and the staging dance around it.

The fetcher is a shell command read from `$TAPEDECK_HOME/config.toml` — never a
hardcoded yt-dlp invocation — and it always downloads into a staging directory
beside the library entry. Only a complete fetch (a video plus normalized
metadata) is moved into `library/<id>/`, so a failure leaves nothing behind
(SPEC-ingest-001) and a re-fetch never half-destroys an entry that was already
good. Staging also keeps the entry to the shape the layout contract names: the
fetcher's own leftovers (info.json, .part files) stay out of the library.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from .meta import META_NAME
from .sources import watch_url

CONFIG_NAME = "config.toml"
SECTION = "ingest"
KEY = "fetcher_command"
VIDEO_STEM = "video"
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp")
STDERR_FD = 2

# The cli writes this into config.toml on first run (it owns that file); it lives
# here as the documented shape of the seam — env in, `video.<ext>` + info.json out.
DEFAULT_FETCHER_COMMAND = (
    'yt-dlp --no-playlist --write-info-json -f "bv*+ba/b" '
    '-o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'
)


class ConfigError(ValueError):
    """The fetcher seam is not configured."""


class FetchError(RuntimeError):
    """The fetcher ran but did not deliver a video."""


def fetcher_command(home: Path) -> str:
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    command = section.get(KEY) if isinstance(section, dict) else None
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"no fetcher configured — set [{SECTION}] {KEY} in {path}")
    return command


def is_video(path: Path) -> bool:
    return path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO


def has_video(entry: Path) -> bool:
    return entry.is_dir() and any(is_video(path) for path in entry.iterdir())


def stage(library: Path, video_id: str) -> Path:
    """A staging dir inside library/ — same filesystem, so the commit is a rename.
    The leading dot keeps a crashed fetch out of any `library/*/` listing."""
    library.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{video_id}.", suffix=".partial", dir=library))


def run(command: str, home: Path, video_id: str, dest: Path) -> None:
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_VIDEO_URL": watch_url(video_id),
        "TAPEDECK_DEST": str(dest),
    }
    try:
        # Download chatter is progress, not output: the fetcher's stdout goes to
        # stderr so ours stays the entry path alone.
        result = subprocess.run(command, shell=True, cwd=dest, env=env, stdout=STDERR_FD)
    except OSError as exc:
        raise FetchError(f"could not run the fetcher — {exc}") from exc
    if result.returncode != 0:
        raise FetchError(f"the fetcher exited {result.returncode}: {command}")


def find_video(dest: Path) -> Path:
    videos = sorted(path for path in dest.iterdir() if is_video(path))
    if not videos:
        raise FetchError(f"the fetcher wrote no {VIDEO_STEM}.<ext> in {dest}")
    return videos[0]


def commit(staging: Path, entry: Path) -> Path:
    """Move the finished entry into place, leaving other components' files alone."""
    for path in staging.iterdir():
        if is_video(path) or path.name == META_NAME:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if not entry.exists():
        entry.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, entry)  # atomic: the entry appears whole or not at all
        return entry
    # A re-fetch: swap our own files only — transcript.json is transcribe's to keep.
    for stale in entry.iterdir():
        if is_video(stale):
            stale.unlink()
    # meta.json last, so an interrupted swap leaves an entry that reads as incomplete
    # and is re-fetched rather than one that lies about the video beside it.
    for path in sorted(staging.iterdir(), key=lambda p: p.name == META_NAME):
        os.replace(path, entry / path.name)
    staging.rmdir()
    return entry
