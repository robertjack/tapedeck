"""The `[ask]` seams (SPEC-core-004): the probabilistic steps, held at arm's length.

Both modes end at a shell command read from `$TAPEDECK_HOME/config.toml` — never a
hardcoded `claude -p`. Each is handed its text on stdin and gives back prose on
stdout; its stderr is the user's to read. Nothing about answers is decided here:
this module resolves a command and runs it, and everything the result is judged
against was fixed before it ran and is checked after (SPEC-ask-002).

The librarian runs with cwd set to the library home, and that is the whole of what
it is given: the files are there, the brief it works to is the `CLAUDE.md` there,
and tapedeck adds no prompt of its own. The answerer gets no cwd — its sources
arrive on stdin.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"
SECTION = "ask"
LIBRARIAN_KEY = "librarian_command"
ANSWERER_KEY = "answerer_command"

# What the cli writes into config.toml on first run (it owns that file); the pair is
# here as the documented shape of each seam. The librarian needs tools to read the
# library it stands in; the answerer needs none — its sources are on stdin.
DEFAULT_LIBRARIAN_COMMAND = 'claude -p --allowedTools "Read,Grep,Glob"'
DEFAULT_ANSWERER_COMMAND = "claude -p"


class ConfigError(ValueError):
    """A seam that is not configured — the request cannot be attempted as it stands."""


class AnswerError(RuntimeError):
    """A seam that ran but did not deliver an answer."""


def command(home: Path, key: str, label: str) -> str:
    """The configured command for one seam, resolved before any work is done — a
    misconfigured tapedeck should fail on the config, not after the retrieval."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    section = section if isinstance(section, dict) else {}
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"no {label} configured — set [{SECTION}] {key} in {path}")
    return value.strip()


def brief(home: Path) -> Path:
    """The librarian's standing instructions: the grounding rules of SPEC-ask-002
    live in this file rather than in a prompt ask assembles, because the agent reads
    it as the CLAUDE.md of the directory it works in. No brief, no librarian — an
    agent loose in the library without the rules is not a mode tapedeck offers."""
    path = home / BRIEF_NAME
    if not path.is_file():
        raise ConfigError(
            f"no librarian brief at {path} — the cli writes one on first run; "
            "restore it, or write your own"
        )
    return path


def run(command: str, home: Path, stdin: str, label: str, cwd: Path | None = None) -> str:
    """Run one seam with `stdin` on its standard input and return the prose it wrote."""
    env = {**os.environ, "TAPEDECK_HOME": str(home)}
    if cwd is not None:
        # A shell reads its own location from $PWD; ours would misplace the librarian.
        env["PWD"] = str(cwd)
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
        )
    except OSError as exc:
        raise AnswerError(f"could not run the {label} — {exc}") from exc
    if result.returncode != 0:
        raise AnswerError(f"the {label} exited {result.returncode}: {command}")
    answer = (result.stdout or "").strip()
    if not answer:
        raise AnswerError(f"the {label} wrote no answer: {command}")
    return answer
