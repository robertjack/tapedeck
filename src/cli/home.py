"""`$TAPEDECK_HOME` resolution and the first-run scaffold (SPEC-cli-001).

The default home belongs to whoever installed the tool: a plain, visible
directory in their own home, never a path particular to this machine. Every
seam default written here is imported from the component that owns it
(LESSON-0003) rather than re-typed — cli only decides the file they land in.
"""

from __future__ import annotations

import os
from pathlib import Path

from ask.seams import BRIEF_NAME, DEFAULT_ANSWERER_COMMAND, DEFAULT_LIBRARIAN_COMMAND
from ingest.fetch import DEFAULT_FETCHER_COMMAND, DEFAULT_LISTER_COMMAND
from transcribe.transcriber import (
    DEFAULT_MODEL,
    DEFAULT_TRANSCRIBER_COMMAND,
    PARAKEET_MODEL,
    PARAKEET_TRANSCRIBER_COMMAND,
)
from wiki.seams import DEFAULT_MAINTAINER_COMMAND as WIKI_MAINTAINER_COMMAND

CONFIG_NAME = "config.toml"
DISPLAY_DEFAULT_HOME = "~/Tapedeck"


def home_dir() -> Path:
    override = os.environ.get("TAPEDECK_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Tapedeck"


def _toml(command: str) -> str:
    """A TOML literal string — single-quoted, so the double quotes every
    published seam command carries need no escaping."""
    return f"'{command}'"


_DEFAULT_CONFIG = f"""# tapedeck configuration — every external tool sits behind one of these
# seams (SPEC-core-004). Edit any line to swap tools; nothing is hardcoded.

[ingest]
fetcher_command = {_toml(DEFAULT_FETCHER_COMMAND)}
lister_command = {_toml(DEFAULT_LISTER_COMMAND)}

[transcribe]
transcriber_command = {_toml(DEFAULT_TRANSCRIBER_COMMAND)}
model = "{DEFAULT_MODEL}"
# Apple Silicon alternative — parakeet-mlx (~2.4GB download on first use):
# transcriber_command = {_toml(PARAKEET_TRANSCRIBER_COMMAND)}
# model = "{PARAKEET_MODEL}"

[ask]
librarian_command = {_toml(DEFAULT_LIBRARIAN_COMMAND)}
answerer_command = {_toml(DEFAULT_ANSWERER_COMMAND)}

[wiki]
auto = true
maintainer_command = {_toml(WIKI_MAINTAINER_COMMAND)}

[setup]
remedy.yt-dlp = "brew install yt-dlp"
remedy.ffmpeg = "brew install ffmpeg"
remedy.mlx_whisper = "uv tool install mlx-whisper"
remedy.parakeet-mlx = "uv tool install parakeet-mlx"
remedy.claude = "see https://docs.claude.com/en/docs/claude-code for install instructions"
"""

_DEFAULT_BRIEF = """# tapedeck librarian brief

You are answering questions about the videos in this library, and nothing else.

- Answer only from what these videos actually say. If the library does not
  cover the question, say plainly that it is "not in the library" rather
  than guessing or drawing on outside knowledge.
- Cite every claim with an inline markdown deep link —
  [label](https://www.youtube.com/watch?v=<id>&t=<seconds>s) — pointing at
  the moment in the video that supports it. An answer with no citation is
  refused.
- Prefer reading transcripts and archive pages under this library over
  anything you already believe about the topic.
"""


def ensure_home(home: Path) -> None:
    """The scaffold every verb performs on first use (SPEC-cli-001):
    library/, archive/, a commented config.toml, and the librarian's brief.
    Never overwrites what is already there — after the first run, this file
    and this brief are the user's."""
    (home / "library").mkdir(parents=True, exist_ok=True)
    (home / "archive").mkdir(parents=True, exist_ok=True)
    config = home / CONFIG_NAME
    if not config.is_file():
        config.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    brief = home / BRIEF_NAME
    if not brief.is_file():
        brief.write_text(_DEFAULT_BRIEF, encoding="utf-8")
