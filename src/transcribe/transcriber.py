"""The transcriber seam (SPEC-core-004) and the scratch dir around it.

The transcriber is a shell command read from `$TAPEDECK_HOME/config.toml` — never a
hardcoded mlx_whisper invocation. It reads the media at `$TAPEDECK_MEDIA` and writes
whisper-shaped JSON to `$TAPEDECK_OUT`, a path we choose inside a scratch directory
*outside* the library: the tool's own leftovers (srt/vtt/txt siblings, half-written
files) never touch an entry, and nothing reaches transcript.json until that output
has parsed and normalized (SPEC-transcribe-001).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
SECTION = "transcribe"
COMMAND_KEY = "transcriber_command"
MODEL_KEY = "model"
VIDEO_STEM = "video"
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp")
STDERR_FD = 2

# What the cli writes into config.toml on first run (it owns that file); the pair
# lives here as the documented shape of the seam — env in, whisper-shaped JSON out.
# We name $TAPEDECK_OUT after the media stem because mlx_whisper writes
# `<output-dir>/<stem>.json`, so the default command lands on it without renaming.
DEFAULT_TRANSCRIBER_COMMAND = (
    "mlx_whisper --model mlx-community/whisper-large-v3-mlx --output-format json "
    '--output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
)
DEFAULT_MODEL = "mlx-whisper/large-v3"
UNLABELLED_MODEL = "unknown"


class ConfigError(ValueError):
    """The transcriber seam is not configured."""


class TranscribeError(RuntimeError):
    """The transcriber ran but did not deliver usable output."""


def seam(home: Path) -> tuple[str, str]:
    """The configured transcriber command, and the model identity to record with it."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    section = section if isinstance(section, dict) else {}
    command = section.get(COMMAND_KEY)
    if not isinstance(command, str) or not command.strip():
        seat = f"[{SECTION}] {COMMAND_KEY} in {path}"
        raise ConfigError(f"no transcriber configured — set {seat}")
    model = section.get(MODEL_KEY)
    # A seam pointed at some other tool without a label records `unknown` rather than
    # claiming the default model's identity — `model` is what supersession is judged on.
    model = model.strip() if isinstance(model, str) and model.strip() else UNLABELLED_MODEL
    return command.strip(), model


def is_video(path: Path) -> bool:
    return path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO


def find_media(entry: Path, video_id: str) -> Path:
    """The `video.<ext>` this entry is built around — the source we derive from."""
    contents = entry.iterdir() if entry.is_dir() else []
    videos = sorted(path for path in contents if is_video(path))
    if not videos:
        raise TranscribeError(f"{video_id}: no video file in {entry} — run `add` first")
    return videos[0]


def stage() -> Path:
    return Path(tempfile.mkdtemp(prefix="tapedeck-transcribe-"))


def run(command: str, home: Path, video_id: str, media: Path, staging: Path) -> dict:
    """Run the seam over `media` and return whatever JSON it produced."""
    out = staging / f"{media.stem}.json"
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_MEDIA": str(media),
        "TAPEDECK_OUT": str(out),
    }
    try:
        # Transcribers narrate the text as they decode it: their stdout goes to
        # stderr so ours stays the transcript path alone.
        result = subprocess.run(command, shell=True, cwd=staging, env=env, stdout=STDERR_FD)
    except OSError as exc:
        raise TranscribeError(f"could not run the transcriber — {exc}") from exc
    if result.returncode != 0:
        raise TranscribeError(f"the transcriber exited {result.returncode}: {command}")
    if not out.is_file():
        raise TranscribeError(f"the transcriber wrote no JSON to {out}")
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TranscribeError(f"the transcriber's output is not JSON — {exc}") from exc
