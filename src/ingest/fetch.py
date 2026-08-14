"""The external tools ingest reaches for, and the rules about what they leave.

Both tools sit behind command templates in `config.toml` (SPEC-core-004): the
fetcher downloads one video into a destination directory, the lister enumerates a
collection. Neither is ever named in code — swapping yt-dlp for something else is
one edited line in the user's config, and the durable evaluations use that same
seam to inject fakes.

The shipped defaults live here because the shape of a seam belongs to the
component that invokes it; the cli only scaffolds them into a fresh config. The
fetcher default is LESSON-0001 verbatim: YouTube serves 403s for AV1 in this
setup, so avc1 at <=1080p is preferred with plain fallbacks. A solved incident
stays solved only if the fix ships as the default.

Also here: what counts as a downloaded video (SPEC-ingest-001). `video.<ext>` is
the download only when `<ext>` names a container — the suffixes a fetcher leaves
mid-flight or beside the video never are. Every component asks this question, and
they all ask it here.
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
# The siblings a fetcher writes into the same directory: fragments of a download
# in flight, and the sidecars it keeps beside the finished one.
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp", ".description", ".webp", ".jpg", ".png")
STDERR_FD = 2  # a fetcher's chatter is progress, not output: never our stdout

DEFAULT_FETCHER_COMMAND = (
    "yt-dlp --no-playlist --write-info-json "
    '-f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" '
    '-o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'
)
DEFAULT_LISTER_COMMAND = 'yt-dlp --flat-playlist --print "%(id)s" "$TAPEDECK_COLLECTION_URL"'


class ConfigError(ValueError):
    """The seam is not configured — a usage error the user fixes in config.toml."""


class FetchError(RuntimeError):
    """The tool ran and did not deliver. The library is untouched."""


def _seam(home: Path, key: str, label: str, default: str) -> str:
    path = home / CONFIG_NAME
    try:
        with open(path, "rb") as handle:
            config = tomllib.load(handle)
    except OSError:
        config = {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    command = (config.get(SECTION) or {}).get(key)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(
            f"no {label} configured: add [{SECTION}].{key} to {path} — the shipped "
            f"default is: {default}"
        )
    return command


def fetcher(home: Path) -> str:
    return _seam(home, FETCHER_KEY, "fetcher command", DEFAULT_FETCHER_COMMAND)


def lister(home: Path) -> str:
    return _seam(home, LISTER_KEY, "lister command", DEFAULT_LISTER_COMMAND)


def _seam_env(home: Path, **extra: str) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home), **extra}


def stage(library: Path, video_id: str) -> Path:
    """Somewhere to download into, inside the library's own filesystem.

    A staging area anywhere else turns installing the result into a copy across
    devices, and a copy can stop halfway — leaving a truncated video that every
    later run believes. Here the install is a rename. The dot prefix keeps the
    directory out of the library's readers while the download runs.
    """
    library.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".fetching-{video_id}-", dir=library))


def run(command: str, home: Path, video_id: str, url: str, dest: Path) -> None:
    """Fetch one video into `dest`. Raises FetchError unless the tool exits clean."""
    env = _seam_env(
        home, TAPEDECK_VIDEO_ID=video_id, TAPEDECK_VIDEO_URL=url, TAPEDECK_DEST=str(dest)
    )
    result = subprocess.run(command, shell=True, env=env, stdout=STDERR_FD)
    if result.returncode != 0:
        raise FetchError(f"the fetcher failed for {video_id} (exit {result.returncode})")


def collect(command: str, home: Path, url: str) -> str:
    """The lister's stdout for one collection URL, or FetchError if it failed. A
    half-read channel passed off as the whole one is worse than no listing."""
    env = _seam_env(home, TAPEDECK_COLLECTION_URL=url)
    result = subprocess.run(
        command, shell=True, env=env, stdout=subprocess.PIPE, text=True, errors="replace"
    )
    if result.returncode != 0:
        raise FetchError(f"the lister failed for {url} (exit {result.returncode})")
    return result.stdout or ""


def videos(directory: Path) -> list[Path]:
    """The downloaded video files in a directory — the published rule.

    `video.part` is a fetch in flight and `video.info.json` is a sidecar; neither
    is a video, so an entry holding only those has no video and is fetched again.
    """
    contents = sorted(directory.iterdir()) if directory.is_dir() else []
    return [
        path
        for path in contents
        if path.is_file()
        and path.stem == VIDEO_STEM
        and path.suffix
        and path.suffix.lower() not in NOT_VIDEO
    ]


def has_video(directory: Path) -> bool:
    """Whether this directory holds a real download (SPEC-core-003's skip test)."""
    return bool(videos(directory))


def find_video(dest: Path, video_id: str) -> Path:
    """The one video a fetch produced. Nothing usable is a failed fetch."""
    found = videos(dest)
    if not found:
        raise FetchError(f"the fetcher left no video file for {video_id}")
    return found[0]


def read_info(dest: Path, video_id: str) -> dict:
    """The fetcher's metadata sidecar, as it wrote it.

    yt-dlp names it after the output template (`video.info.json`); anything ending
    in `info.json` is the same promise, and a lone `.json` is taken as the sidecar
    too so a thinner fetcher still satisfies the seam.
    """
    candidates = sorted(dest.glob("*.json")) if dest.is_dir() else []
    candidates.sort(key=lambda path: not path.name.endswith(INFO_SUFFIX))
    for path in candidates:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict):
            return document
    raise FetchError(
        f"the fetcher wrote no readable info json for {video_id} — there is no "
        "metadata to build meta.json from"
    )
