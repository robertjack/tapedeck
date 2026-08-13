"""The transcriber seam (SPEC-core-004) and the scratch space around it.

The transcriber is a shell command read from `$TAPEDECK_HOME/config.toml` — never
a hardcoded mlx_whisper invocation. It writes into a scratch directory *outside*
the library, and nothing lands in `library/<id>/` until that output has parsed and
normalized. Transcribing is minutes of GPU time that can die in the middle, and a
half-written transcript.json is worse than none: archive would render it and ask
would cite it, both without a hint that words are missing.
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
# `video.<ext>` names the download; these are the siblings a fetcher leaves that
# are plainly not it (sidecars, part-files, thumbnails).
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp", ".description", ".webp", ".jpg", ".png")
STDERR_FD = 2

# What the cli scaffolds into config.toml on first run (it owns that file); the
# defaults live here because the seam's shape is transcribe's to define.
#
# This is LESSON-0002 verbatim, and none of it is incidental: large-v3 with default
# conditioning falls into repetition loops on long videos, so what ships is turbo
# with conditioning off. `--output-dir "$(dirname "$TAPEDECK_OUT")"` is how a
# whisper CLI is told where to land — it names the file itself, after the input —
# and `out_path` below chooses a $TAPEDECK_OUT that meets it there.
DEFAULT_TRANSCRIBER_COMMAND = (
    "mlx_whisper --model mlx-community/whisper-large-v3-turbo "
    "--condition-on-previous-text False --output-format json "
    '--output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
)
# Recorded in every transcript this command produces. It names the configuration in
# use rather than just the weights, because supersession is judged on this string:
# a transcript made with conditioning left on must not be indistinguishable from
# one made without it (LESSON-0002).
DEFAULT_MODEL = "mlx-whisper/large-v3-turbo"


class ConfigError(ValueError):
    """The transcriber seam is not configured."""


class TranscribeError(RuntimeError):
    """The transcriber ran but did not deliver a usable transcript."""


def media(entry: Path, video_id: str) -> Path:
    """The video this transcript comes from — the source of truth (SPEC-core-002).

    The layout contract names it `video.<ext>` without fixing the container, so it
    is found by stem, with the sidecars that may sit beside it excluded by suffix.
    """
    contents = entry.iterdir() if entry.is_dir() else []
    found = sorted(
        path
        for path in contents
        if path.is_file() and path.stem == VIDEO_STEM and path.suffix.lower() not in NOT_VIDEO
    )
    if not found:
        raise TranscribeError(f"{video_id}: no video file in {entry} — nothing to transcribe")
    return found[0]


def _section(home: Path) -> dict:
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"cannot read {path} for the transcriber command — {exc}") from exc
    section = config.get(SECTION)
    return section if isinstance(section, dict) else {}


def _label(section: dict, command: str, path: Path) -> str:
    """The model label stamped on every transcript this run produces.

    LESSON-0002: the label decides whether a later transcript supersedes an older
    one, so it has to name the configuration actually in use. We can supply it for
    the command we ship — we know what that one runs. For a command someone has
    edited, a default would stamp `mlx-whisper/large-v3-turbo` onto transcripts
    that never saw it, quietly making them un-supersedable, so an unlabelled custom
    seam is a configuration error rather than a guess.
    """
    label = section.get(MODEL_KEY)
    if isinstance(label, str) and label.strip():
        return label.strip()
    if command == DEFAULT_TRANSCRIBER_COMMAND:
        return DEFAULT_MODEL
    raise ConfigError(
        f"the transcriber command is not the one tapedeck ships — set [{SECTION}] "
        f"{MODEL_KEY} in {path} to name the model it really runs, or its transcripts "
        "are labelled with a model that never saw them"
    )


def seam(home: Path) -> tuple[str, str]:
    """The configured transcriber command, and the model label to record with it."""
    path = home / CONFIG_NAME
    section = _section(home)
    command = section.get(COMMAND_KEY)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"no transcriber configured — set [{SECTION}] {COMMAND_KEY} in {path}")
    command = command.strip()
    return command, _label(section, command, path)


def stage() -> Path:
    return Path(tempfile.mkdtemp(prefix="tapedeck-transcribe-"))


def out_path(staging: Path, source: Path) -> Path:
    """Where the transcriber is told to write ($TAPEDECK_OUT).

    Outside the library, so a run that dies halfway leaves nothing beside the video.
    The stem is the media's because that is the one convention every whisper CLI
    shares: pointed at an output directory it writes `<input-stem>.json` there.
    Handing it `<staging>/video.json` makes the file it names and the file we read
    the same file, so the shipped default needs no wrapper script to bridge them.
    """
    return staging / f"{source.stem}.json"


def run(command: str, home: Path, video_id: str, source: Path, out: Path) -> None:
    """Run the seam over one video. Raises TranscribeError unless it exits clean."""
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_MEDIA": str(source),
        "TAPEDECK_OUT": str(out),
    }
    try:
        # Whisper narrates decoded segments as it goes; our stdout carries the
        # transcript path alone, so the child's joins the diagnostics on stderr.
        # cwd is the staging dir so anything it writes relative lands there too.
        result = subprocess.run(command, shell=True, cwd=out.parent, env=env, stdout=STDERR_FD)
    except OSError as exc:
        raise TranscribeError(f"could not run the transcriber — {exc}") from exc
    if result.returncode != 0:
        raise TranscribeError(f"the transcriber exited {result.returncode}: {command}")


def read_output(out: Path, video_id: str) -> dict:
    """The whisper-shaped JSON the transcriber left at $TAPEDECK_OUT."""
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TranscribeError(
            f"{video_id}: the transcriber exited clean but wrote no output at {out}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise TranscribeError(
            f"{video_id}: the transcriber's output is not readable JSON — {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise TranscribeError(f"{video_id}: the transcriber's output is not a JSON object")
    return payload
