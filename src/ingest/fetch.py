"""The external-tool seams (SPEC-core-004) and the staging ground around them.

Both tools ingest reaches for are shell commands read from
`$TAPEDECK_HOME/config.toml` — never a hardcoded yt-dlp invocation. The fetcher
downloads one video; the lister enumerates a collection. The fetcher works in a
scratch directory *outside* the library, and nothing moves into `library/<id>/`
until the download is whole and its metadata has normalized. Downloading is the
one step in tapedeck that routinely dies halfway (network, 403s, a full disk);
staging is what keeps that from leaving a half-entry behind for every later verb
to trip over.
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
FETCHER_KEY = "fetcher_command"
LISTER_KEY = "lister_command"
VIDEO_STEM = "video"
INFO_SUFFIX = "info.json"
# `video.<ext>` names the download; these are the siblings a fetcher leaves that
# are plainly not it (part-files, sidecars, thumbnails).
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp", ".description", ".webp", ".jpg", ".png")
STDERR_FD = 2

# What the cli scaffolds into config.toml on first run (it owns that file); the
# defaults live here because the seams' shapes are ingest's to define.
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
# `--flat-playlist` is the whole point: ids for a thousand-video channel without
# resolving a single one of them. One id per line is all ingest reads.
DEFAULT_LISTER_COMMAND = 'yt-dlp --flat-playlist --print "%(id)s" "$TAPEDECK_COLLECTION_URL"'


class ConfigError(ValueError):
    """A seam this run needs is not configured."""


class FetchError(RuntimeError):
    """A seam ran but did not deliver what it promises."""


def _seam(home: Path, key: str, label: str) -> str:
    """The configured command for one seam."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"cannot read {path} for the {label} command — {exc}") from exc
    section = config.get(SECTION)
    section = section if isinstance(section, dict) else {}
    command = section.get(key)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"no {label} configured — set [{SECTION}] {key} in {path}")
    return command.strip()


def fetcher(home: Path) -> str:
    return _seam(home, FETCHER_KEY, "fetcher")


def lister(home: Path) -> str:
    return _seam(home, LISTER_KEY, "lister")


def stage() -> Path:
    return Path(tempfile.mkdtemp(prefix="tapedeck-ingest-"))


def run(command: str, home: Path, video_id: str, url: str, dest: Path) -> None:
    """Run the fetcher into `dest`. Raises FetchError unless it exits clean."""
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


def collect(command: str, home: Path, url: str) -> str:
    """Run the lister over a collection URL and return its stdout.

    Here stdout is the answer, not noise, so it is captured while the tool's own
    narration goes on flowing to our stderr. A lister that exits non-zero has
    printed a truncated list at best, so it raises and the caller prints nothing:
    half a channel silently passed off as the whole one is the failure that would
    go unnoticed.
    """
    env = {**os.environ, "TAPEDECK_HOME": str(home), "TAPEDECK_COLLECTION_URL": url}
    try:
        result = subprocess.run(command, shell=True, env=env, stdout=subprocess.PIPE, text=True)
    except OSError as exc:
        raise FetchError(f"could not run the lister — {exc}") from exc
    if result.returncode != 0:
        raise FetchError(f"the lister exited {result.returncode}: {command}")
    return result.stdout or ""


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
