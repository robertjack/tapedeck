"""The two commands wiki runs, neither of them written down in code.

`[wiki].maintainer_command` is the agent that does the writing (SPEC-core-004). It is
handed the wiki, the video and a task, and nothing it says is believed: what it wrote
is judged afterwards by the gate. The published default gives an agent that can read
the library and write the wiki and nothing else; a user who prefers another agent, or
a script, edits the line.

ask is the other, and it is not a configured seam but a component boundary. Whether a
deep link is real — where a URL ends when a full stop follows it, what an unknown
duration waives — is ask's vocabulary, settled in contracts/ask-citations.md and
published as `ask verify` precisely so this component can ask instead of re-deriving
(SPEC-ask-005, LESSON-0003). `$TAPEDECK_ASK_CMD` overrides how it is reached, which is
the same override every component boundary documents and the seam a fake ask arrives
through.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
SECTION = "wiki"
MAINTAINER_KEY = "maintainer_command"
ASK_CMD_ENV = "TAPEDECK_ASK_CMD"
ASK_MODULE = "ask"
VERIFY = "verify"

DEFAULT_MAINTAINER_COMMAND = (
    'claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"'
)


class ConfigError(ValueError):
    """A seam that is not configured — the request cannot be attempted as it stands."""


class MaintainerFailed(RuntimeError):
    """The agent ran and did not finish. Whatever it left behind is rolled back."""


def maintainer_command(home: Path) -> str:
    """The configured maintainer, resolved before anything is written — an
    unconfigured tapedeck should fail on the config, not halfway through a filing."""
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:  # unreadable, undecodable, or not TOML
        raise ConfigError(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    value = section.get(MAINTAINER_KEY) if isinstance(section, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"no wiki maintainer configured — set [{SECTION}] {MAINTAINER_KEY} in "
            f"{path} to the shell command that runs your agent, for example:\n"
            f"  {MAINTAINER_KEY} = '{DEFAULT_MAINTAINER_COMMAND}'"
        )
    return value.strip()


def run_maintainer(
    command: str, home: Path, wiki: Path, video_id: str, archive_page: Path, task: str
) -> None:
    """Turn the agent loose inside the wiki with the task on stdin.

    The whole interface is here: where it runs, what it is working on, and what it has
    been asked to do. Its own chatter is captured rather than printed, because this
    command's stdout belongs to the user, and it is relayed only when the run fails.
    """
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_WIKI": str(wiki),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_ARCHIVE_PAGE": str(archive_page),
        # a shell reads its own location from $PWD; ours would misplace the agent
        "PWD": str(wiki),
    }
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=wiki,
            env=env,
            input=task,
            text=True,
            stdout=subprocess.PIPE,
        )
    except OSError as exc:
        raise MaintainerFailed(f"could not run the maintainer — {exc}") from exc
    if result.returncode != 0:
        said = (result.stdout or "").strip()
        raise MaintainerFailed(
            f"the maintainer exited {result.returncode}: {command}"
            + (f"\n{said}" if said else "")
        )


def ask_verify(home: Path, text: str) -> str | None:
    """ask's verdict on one page's deep links: None when they all hold, else what ask
    said about them, relayed rather than replaced by a message of our own.

    No `--require-citation`: a wiki page is not an answer, so a note that cites nothing
    has made no claim to check. One page's text per invocation — the cost of a filing
    grows with the wiki, and it buys the guarantee that the rules for reading a
    citation live in exactly one component (LESSON-0003).
    """
    command = shlex.split(os.environ.get(ASK_CMD_ENV) or f"{sys.executable} -m {ASK_MODULE}")
    try:
        result = subprocess.run(
            [*command, VERIFY],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "TAPEDECK_HOME": str(home)},
        )
    except OSError as exc:
        return f"could not reach ask to verify the deep links — {exc}"
    if result.returncode == 0:
        return None
    said = (result.stderr or "").strip() or (result.stdout or "").strip()
    return said or f"ask verify exited {result.returncode}"
