"""The `[wiki]` maintainer seam, and the one question wiki puts to ask.

The maintainer is a seam like every other (SPEC-core-004): a shell command read
from `$TAPEDECK_HOME/config.toml`, never a hardcoded agent, run with cwd set to
the wiki so its own paths are the wiki's paths, the task on stdin and the video
in its environment. Nothing about the wiki it produces is decided here — this
module resolves a command and runs it, and everything the result is judged
against is checked afterwards by the gate.

`DEFAULT_MAINTAINER_COMMAND` is published for cli to scaffold into a fresh
config.toml with the rest of the commented defaults. The shape of a seam belongs
to the component that runs it; writing config.toml belongs to cli, and wiki never
touches that file.

The other direction is the citation check. Whether a deep link is real — where
the URL ends when sentence punctuation follows it, what an unknown duration
waives — is settled in contracts/ask-citations.md and published as `ask verify`
(SPEC-ask-005) precisely so this component can ask instead of re-deriving. A
second regex for YouTube links living here would be the defect whether or not it
currently agreed (LESSON-0003), and it is the reason a change to the citation
rules changes this gate with no clause and no code in this component.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from . import Failure, Usage

SECTION = "wiki"
MAINTAINER_KEY = "maintainer_command"
CONFIG_NAME = "config.toml"
# How ask is reached, and the override the evals inject a fake ask through.
ASK_ENV = "TAPEDECK_ASK_CMD"
VERIFY = "verify"

# An agent that can read the library and write the wiki, and nothing else.
DEFAULT_MAINTAINER_COMMAND = (
    'claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"'
)

TASK = """\
File the library video {video_id} into this wiki.

Read its archive page first — {page} — which is the video rendered as prose, with
a deep link into every section. Then write the wiki up to whatever CLAUDE.md in
this directory asks of a filing: that file is the brief, it is the user's, and it
is the only instruction that matters about what a page should say.

Two things are true of every filing whatever the brief says. There must be a
`sources/{video_id}.md` when you finish, carrying at least one deep link into
{video_id} itself — copy links out of the archive page rather than composing
them. And `log.md` must gain an entry, appended at the end and never anywhere
else, opening exactly:

## [{today}] file | {video_id}

Everything you write is checked over the whole wiki and then committed as one
commit, or rejected entire: wiki links must resolve, deep links must be real
moments in real library videos, `index.md` must link every page but the three at
the top level, and CLAUDE.md must come out byte-for-byte as you found it.
"""


class ConfigError(Usage):
    """A seam that is not configured — the request cannot be attempted as it is."""


class MaintainerError(Failure):
    """The maintainer ran and did not come back with a wiki to judge."""


class AskUnreachable(Failure):
    """ask could not be reached, so no citation in the wiki can be checked."""


def maintainer_command(home: Path) -> str:
    """The configured maintainer, resolved before anything is scaffolded, run or
    destroyed — a misconfigured tapedeck should fail on the config."""
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
            f"{path} to a shell command that edits the wiki, for example: "
            f"{DEFAULT_MAINTAINER_COMMAND}"
        )
    return value.strip()


def task(video_id: str, page: Path, today: str) -> str:
    return TASK.format(video_id=video_id, page=page, today=today)


def run_maintainer(
    command: str, home: Path, wiki: Path, video_id: str, page: Path, today: str
) -> None:
    """Turn the agent loose in the wiki. A nonzero exit is a failed operation:
    whatever a crashed agent left half-written is not the wiki's problem."""
    env = {
        **os.environ,
        "TAPEDECK_HOME": str(home),
        "TAPEDECK_WIKI": str(wiki),
        "TAPEDECK_VIDEO_ID": video_id,
        "TAPEDECK_ARCHIVE_PAGE": str(page),
        # A shell reads its own location from $PWD; ours would misplace the agent.
        "PWD": str(wiki),
    }
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=wiki,
            env=env,
            input=task(video_id, page, today),
            text=True,
            # The agent's own chatter is not the product and does not belong on
            # this component's stdout; what it wrote is read off the disk.
            stdout=subprocess.PIPE,
        )
    except OSError as exc:
        raise MaintainerError(f"could not run the maintainer — {exc}") from exc
    if result.returncode != 0:
        raise MaintainerError(f"the maintainer exited {result.returncode}: {command}")


def ask_argv() -> list[str]:
    override = os.environ.get(ASK_ENV)
    return shlex.split(override) if override else [sys.executable, "-m", "ask"]


def verify(home: Path, text: str) -> str | None:
    """ask's verdict on the deep links in one page's text: None when they hold,
    and otherwise what ask said about them, relayed rather than replaced by a
    message of this component's own.

    `--require-citation` is deliberately absent. A wiki page is not an answer: a
    note that cites nothing has made no claim, so the only question here is
    whether the links a page does carry are true.
    """
    try:
        result = subprocess.run(
            [*ask_argv(), VERIFY],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "TAPEDECK_HOME": str(home)},
        )
    except OSError as exc:
        raise AskUnreachable(
            f"could not reach `ask {VERIFY}` to check the wiki's citations — {exc}"
        ) from exc
    if result.returncode == 0:
        return None
    said = (result.stderr or result.stdout).strip()
    return " ".join((said or f"ask {VERIFY} exited {result.returncode}").split())
