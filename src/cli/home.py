"""`$TAPEDECK_HOME` resolution and the first-run scaffold (SPEC-cli-001).

The default home is a plain, visible directory in whoever installed the tool's
own home — never the author's `~/dev/storage/tapedeck` (that default is stale;
this module is the sole authority now). Every seam default written into the
scaffolded `config.toml` is imported from the component that owns that seam's
shape (LESSON-0003): this file duplicates none of them.
"""

from __future__ import annotations

import os
from pathlib import Path

import ingest
import transcribe
from ask import seams as ask_seams
from wiki import seams as wiki_seams

HOME_ENV = "TAPEDECK_HOME"
DEFAULT_HOME_NAME = "Tapedeck"
CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"

BRIEF = """\
# Librarian brief

Answer only from this library: `library/` and the pages rendered under
`archive/`. Never use outside knowledge. Cite every claim with an inline deep
link — `[label](https://www.youtube.com/watch?v=<id>&t=<seconds>s)` — built
from the archive page's own section headings. If the sources here do not
answer the question, reply exactly: not in the library
"""

CONFIG_TEMPLATE = """\
# tapedeck config — every external tool sits behind one of these command
# templates (SPEC-core-004). Edit any line freely; comments are yours to
# keep or drop.

[ingest]
# fetcher_command downloads one video (SPEC-ingest-001). This default carries
# two solved YouTube incidents so a fresh install never re-suffers them:
# LESSON-0001's avc1 preference and LESSON-0006's embedded-client lead.
fetcher_command = '{fetcher}'
# lister_command enumerates a playlist or channel URL (SPEC-ingest-002).
lister_command = '{lister}'

[transcribe]
# transcriber_command derives a transcript (SPEC-core-004). LESSON-0002:
# turbo weights with conditioning off avoid large-v3's repetition loops.
transcriber_command = '{transcriber}'
model = "{model}"
# Apple's parakeet-mlx is the published alternative (SPEC-transcribe-002) —
# swap to it by uncommenting these two lines instead of the pair above:
# transcriber_command = '{parakeet_cmd}'
# model = "{parakeet_model}"

[ask]
librarian_command = '{librarian}'
answerer_command = '{answerer}'

[wiki]
# maintainer_command is the agent that writes and later tends this wiki.
maintainer_command = '{maintainer}'
# auto files each video `add` completes; an absent key also reads true.
auto = true

[setup]
# remedy.<executable> installs a tool `doctor` found missing; `tapedeck
# setup` prints these and `--yes` runs them. update.<executable> upgrades
# one already on PATH (`tapedeck setup --refresh`).
remedy.yt-dlp = "brew install yt-dlp"
remedy.ffmpeg = "brew install ffmpeg"
remedy.mlx_whisper = "uv tool install mlx-whisper"
remedy.parakeet-mlx = "uv tool install parakeet-mlx"
remedy.claude = "see https://docs.claude.com/en/docs/claude-code/setup"
update.yt-dlp = "brew upgrade yt-dlp"
update.ffmpeg = "brew upgrade ffmpeg"
update.mlx_whisper = "uv tool upgrade mlx-whisper"
update.parakeet-mlx = "uv tool upgrade parakeet-mlx"
"""


def default_home() -> Path:
    return Path.home() / DEFAULT_HOME_NAME


def home_dir() -> Path:
    raw = os.environ.get(HOME_ENV)
    return Path(raw).expanduser() if raw else default_home()


def _config_text() -> str:
    return CONFIG_TEMPLATE.format(
        fetcher=ingest.DEFAULT_FETCHER_COMMAND,
        lister=ingest.DEFAULT_LISTER_COMMAND,
        transcriber=transcribe.DEFAULT_TRANSCRIBER_COMMAND,
        model=transcribe.DEFAULT_MODEL,
        parakeet_cmd=transcribe.PARAKEET_TRANSCRIBER_COMMAND,
        parakeet_model=transcribe.PARAKEET_MODEL,
        librarian=ask_seams.DEFAULT_LIBRARIAN_COMMAND,
        answerer=ask_seams.DEFAULT_ANSWERER_COMMAND,
        maintainer=wiki_seams.DEFAULT_MAINTAINER_COMMAND,
    )


def ensure_home(home: Path) -> Path:
    """The first-run scaffold every verb performs: the home directories, a
    default `config.toml`, and the librarian's brief — created once, then
    left to the user (SPEC-cli-001, SPEC-ask-002)."""
    (home / "library").mkdir(parents=True, exist_ok=True)
    (home / "archive").mkdir(parents=True, exist_ok=True)
    config = home / CONFIG_NAME
    if not config.is_file():
        config.write_text(_config_text(), encoding="utf-8")
    brief = home / BRIEF_NAME
    if not brief.is_file():
        brief.write_text(BRIEF, encoding="utf-8")
    return home
