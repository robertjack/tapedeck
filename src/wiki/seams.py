"""The two commands wiki runs, and neither of them is hardcoded.

`[wiki].maintainer_command` (SPEC-core-004) is the agent that writes this wiki —
and, unchanged, the agent that tends it. A second seam would be a second voice:
a tender configured apart from the maintainer would read the brief the maintainer
follows and answer to a different one, and the wiki would accumulate in two
registers. What distinguishes the runs is the task on stdin, which names the mode;
everything else about the invocation is the same interface. `config.toml` is cli's
file and wiki only reads a key out of it — a wiki that cannot find its seam says
which key is missing rather than inventing a default and spending a run on it.

`ask verify` is the other command, and it is here for the opposite reason. Reading
a citation — where a URL ends when a sentence's punctuation follows it, what an
unknown duration waives — is settled in contracts/ask-citations.md and published
as a verb precisely so this component can ask instead of re-deriving (LESSON-0003).
A second YouTube-link regex living here would be the defect whether or not it
currently agreed. It is invoked as `$TAPEDECK_ASK_CMD` when that variable is set
and as `<current python> -m ask` otherwise, which is the seam a fake ask is
injected through and the reason a change to the citation rules changes this gate
with no code here at all.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from . import Failure, Usage

CONFIG = "config.toml"
SECTION = "wiki"
MAINTAINER_KEY = "maintainer_command"
ASK_CMD = "TAPEDECK_ASK_CMD"
ASK_MODULE = "ask"
VERIFY = "verify"

# What cli scaffolds into a fresh config.toml with the rest of the commented
# defaults: an agent that can read the library and write the wiki, and nothing
# else. A user who prefers another agent, or a script, edits the line.
DEFAULT_MAINTAINER_COMMAND = (
    'claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"'
)


def maintainer_command(home: Path) -> str:
    """The configured maintainer, resolved before any work is done — a run that
    cannot reach an agent should fail on the config, not after the scaffold."""
    path = home / CONFIG
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:
        raise Usage(f"{path} is unreadable — {exc}") from exc
    section = config.get(SECTION)
    value = section.get(MAINTAINER_KEY) if isinstance(section, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise Usage(
            f"no wiki maintainer configured — set [{SECTION}] {MAINTAINER_KEY} in "
            f"{path} to the shell command that runs your agent, e.g. "
            f'{MAINTAINER_KEY} = "{DEFAULT_MAINTAINER_COMMAND}"'
        )
    return value.strip()


def run_maintainer(
    command: str,
    home: Path,
    wiki: Path,
    task: str,
    video_id: str | None = None,
    archive_page: Path | None = None,
) -> tuple[int, str]:
    """Run the agent from inside the wiki with the task on stdin.

    Four variables for a filing, two for a tend: there is no `TAPEDECK_VIDEO_ID`
    on a run that is about no video, because a variable naming one would be a lie
    about the scope of the run. Returns its exit code and its stdout; what it did
    to the wiki is judged afterwards and never taken on trust.
    """
    env = {**os.environ, "TAPEDECK_HOME": str(home), "TAPEDECK_WIKI": str(wiki)}
    # A shell reads its own location from $PWD; ours would misplace the agent.
    env["PWD"] = str(wiki)
    for key, value in (
        ("TAPEDECK_VIDEO_ID", video_id),
        ("TAPEDECK_ARCHIVE_PAGE", None if archive_page is None else str(archive_page)),
    ):
        env.pop(key, None)
        if value is not None:
            env[key] = value
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
        raise Failure(f"could not run the maintainer — {exc}") from exc
    return result.returncode, result.stdout or ""


def _ask_argv() -> list[str]:
    override = os.environ.get(ASK_CMD)
    if override and override.strip():
        return shlex.split(override)
    return [sys.executable, "-m", ASK_MODULE]


def unverifiable(home: Path, text: str) -> str | None:
    """ask's verdict on one page's deep links: None when they all hold, and its
    own words when they do not.

    `--require-citation` is deliberately absent. A wiki page is not an answer: a
    note that cites nothing has made no claim, and the only question here is
    whether the links a page does carry are true.
    """
    try:
        result = subprocess.run(
            [*_ask_argv(), VERIFY],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "TAPEDECK_HOME": str(home)},
        )
    except OSError as exc:
        return f"could not run `ask {VERIFY}` to check this page's citations — {exc}"
    if result.returncode == 0:
        return None
    said = (result.stderr or "").strip() or (result.stdout or "").strip()
    # Relayed rather than replaced: a message of this component's own would be a
    # second opinion about a question this component does not answer.
    return said or f"ask {VERIFY} exited {result.returncode} on this page"
