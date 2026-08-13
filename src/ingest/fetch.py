"""The fetcher seam (SPEC-core-004) and the staging ground around it.

The fetcher is a shell command read from `$TAPEDECK_HOME/config.toml` — never a
hardcoded yt-dlp invocation. It downloads into a scratch directory *outside* the
library, and nothing moves into `library/<id>/` until the download is whole and
its metadata has normalized. Downloading is the one step in tapedeck that
routinely dies halfway (network, 403s, a full disk); staging is what keeps that
from leaving a half-entry behind for every later verb to trip over.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
SECTION = "ingest"
COMMAND_KEY = "fetcher_command"
VIDEO_STEM = "video"
INFO_SUFFIX = "info.json"
# `video.<ext>` names the download; these are the siblings a fetcher leaves that
# are plainly not it (part-files, sidecars, thumbnails).
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp", ".description", ".webp", ".jpg", ".png")
STDERR_FD = 2

# What the cli scaffolds into config.toml on first run (it owns that file); the
# default lives here because the seam's shape is ingest's to define.
#
# The format selector is LESSON-0001 and is not cosmetic: YouTube serves 403s on
# AV1 streams in this setup, so the default prefers avc1 at <=1080p and falls
# back twice. Shipping the naive `bv*+ba/b` would make every fresh install
# re-suffer an incident that has already been solved once.
DEFAULT_FETCHER_COMMAND = (
    "yt-dlp --no-playlist --write-info-json "
    '-f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" '
    '-o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'
)


class ConfigError(ValueError):
    """The fetcher seam is not configured."""


class FetchError(RuntimeError):
    """The fetcher ran but did not deliver a usable video and its metadata."""


def seam(home: Path) -> str:
    """The configured fetcher command."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"cannot read {path} for the fetcher command — {exc}") from exc
    section = config.get(SECTION)
    section = section if isinstance(section, dict) else {}
    command = section.get(COMMAND_KEY)
    if not isinstance(command, str) or not command.strip():
        seat = f"[{SECTION}] {COMMAND_KEY} in {path}"
        raise ConfigError(f"no fetcher configured — set {seat}")
    return command.strip()


def stage() -> Path:
    return Path(tempfile.mkdtemp(prefix="tapedeck-ingest-"))


def run(command: str, home: Path, video_id: str, url: str, dest: Path) -> None:
    """Run the seam into `dest`. Raises FetchError unless it exits clean."""
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_VIDEO_URL": url,
        "TAPEDECK_DEST": str(dest),
    }
    try:
        # A downloader narrates progress on stdout; ours carries the entry path
        # alone, so the child's goes to stderr with the rest of the noise. cwd is
        # the staging dir so anything it writes relative lands there too.
        result = subprocess.run(command, shell=True, cwd=dest, env=env, stdout=STDERR_FD)
    except OSError as exc:
        raise FetchError(f"could not run the fetcher — {exc}") from exc
    if result.returncode != 0:
        raise FetchError(f"the fetcher exited {result.returncode}: {command}")


def videos(directory: Path) -> list[Path]:
    """Every `video.<ext>` in a directory — the download, wherever it landed."""
    contents = directory.iterdir() if directory.is_dir() else []
    return sorted(
        path
        for path in contents
        if path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO
    )


def has_video(directory: Path) -> bool:
    return bool(videos(directory))


def find_video(dest: Path, video_id: str) -> Path:
    found = videos(dest)
    if not found:
        raise FetchError(f"{video_id}: the fetcher produced no video file in {dest}")
    return found[0]


def read_info(dest: Path, video_id: str) -> dict:
    """The metadata sidecar the fetcher left beside the video. yt-dlp's
    `--write-info-json` lands on `video.info.json`; a hand-rolled fetcher may
    write a plain `info.json`. Either is the same JSON object to us."""
    contents = dest.iterdir() if dest.is_dir() else []
    found = sorted(p for p in contents if p.is_file() and p.name.endswith(INFO_SUFFIX))
    if not found:
        raise FetchError(f"{video_id}: the fetcher wrote no info.json in {dest} — no metadata")
    try:
        return json.loads(found[0].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FetchError(f"{video_id}: {found[0].name} is not readable JSON — {exc}") from exc
