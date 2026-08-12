"""The answerer seam (SPEC-core-004): the one probabilistic step, held at arm's length.

The answerer is a shell command read from `$TAPEDECK_HOME/config.toml` — never a
hardcoded `claude -p`. It is handed the assembled prompt on stdin and gives back
prose on stdout; it is told nothing else, is asked for nothing else, and its
stderr is the user's to see. Everything the answer is judged against — which
chunks it may speak from, which markers exist, what the Sources section says —
was decided before it ran and is checked after (SPEC-ask-002).

A seam that exits non-zero or says nothing has not answered, and ask reports that
rather than printing an empty answer under a full list of sources.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
SECTION = "ask"
COMMAND_KEY = "answerer_command"

# What the cli writes into config.toml on first run (it owns that file); the
# default lives here as the documented shape of the seam — prompt in, prose out.
DEFAULT_ANSWERER_COMMAND = "claude -p"


class ConfigError(ValueError):
    """The answerer seam is not configured."""


class AnswerError(RuntimeError):
    """The answerer ran but did not deliver an answer."""


def seam(home: Path) -> str:
    """The configured answerer command — resolved before retrieval, so a
    misconfigured tapedeck fails on the config rather than after the work."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    section = section if isinstance(section, dict) else {}
    command = section.get(COMMAND_KEY)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"no answerer configured — set [{SECTION}] {COMMAND_KEY} in {path}")
    return command.strip()


def run(command: str, home: Path, prompt: str) -> str:
    """Run the seam with `prompt` on stdin and return the prose it wrote."""
    env = {**os.environ, "TAPEDECK_HOME": str(home)}
    try:
        result = subprocess.run(
            command, shell=True, env=env, input=prompt, text=True, stdout=subprocess.PIPE
        )
    except OSError as exc:
        raise AnswerError(f"could not run the answerer — {exc}") from exc
    if result.returncode != 0:
        raise AnswerError(f"the answerer exited {result.returncode}: {command}")
    answer = (result.stdout or "").strip()
    if not answer:
        raise AnswerError(f"the answerer wrote no answer: {command}")
    return answer
