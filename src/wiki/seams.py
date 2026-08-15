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

A maintainer run is watched, not awaited (SPEC-wiki-007). `run_maintainer`
announces the run on stderr before the process starts, then reads its stdout line
by line as it arrives: a line that parses as a Claude Code stream event becomes
one compact progress line the moment it lands, never batched until exit. The run's
product — what a caller like `tend` relays to the user — is the result event's
text when the whole stdout parsed as such a stream, and the raw stdout byte for
byte otherwise, so a maintainer that narrates nothing loses nothing.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
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
# else — streaming its own progress so a fresh install watches it work without
# being asked to configure anything (SPEC-wiki-007). A user who prefers another
# agent, or prefers the silence, edits the line.
DEFAULT_MAINTAINER_COMMAND = (
    'claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit" '
    "--output-format stream-json --verbose"
)

# The event kinds a progress line is drawn from; everything else — the agent's own
# prose among them — passes through unrendered.
_INIT = "system"
_ASSISTANT = "assistant"
_RESULT = "result"
# Recognisable things a tool call's input might carry, tried in this order.
_TOUCHED_KEYS = ("file_path", "path", "pattern", "command", "query", "url", "glob")


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


def _event(line: str) -> dict | None:
    """A line as a Claude Code stream event, or None if it is not one."""
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) and "type" in parsed else None


def _tool_uses(event: dict) -> list[dict]:
    content = (event.get("message") or {}).get("content") or []
    return [item for item in content if isinstance(item, dict) and item.get("type") == "tool_use"]


def _touched(tool_input: dict) -> str:
    for key in _TOUCHED_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _announce_event(event: dict) -> None:
    """One line for the three kinds of event that earn one, printed the moment it
    arrives so progress and the run stay in step. flush=True because stderr here
    is what a caller watches live, not a log written after the fact."""
    kind = event.get("type")
    if kind == _INIT and event.get("subtype") == "init":
        model = event.get("model")
        if model:
            print(f"  · model {model}", file=sys.stderr, flush=True)
    elif kind == _ASSISTANT:
        for tool in _tool_uses(event):
            touched = _touched(tool.get("input") or {})
            name = tool.get("name", "tool")
            print(f"  · {name} {touched}".rstrip(), file=sys.stderr, flush=True)
    elif kind == _RESULT:
        print(f"  · result: {event.get('subtype', 'done')}", file=sys.stderr, flush=True)


def _feed(stdin, text: str) -> None:
    """Write the task on a thread of its own: a maintainer that starts writing
    output before it has finished reading stdin must never deadlock against a
    parent that is still trying to hand it the rest."""
    try:
        stdin.write(text)
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            stdin.close()
        except OSError:
            pass


def run_maintainer(
    command: str,
    home: Path,
    wiki: Path,
    task: str,
    label: str,
    video_id: str | None = None,
    archive_page: Path | None = None,
) -> tuple[int, str]:
    """Run the agent from inside the wiki with the task on stdin, watched rather
    than awaited. `label` is the one line that announces the run before the
    process starts — the filing names its video, a tend names its mode — so
    silence before it is tapedeck settling the cheap questions and silence after
    it is the agent working. Returns the exit code and the run's product; what it
    did to the wiki is judged afterwards by the gate and never taken on trust.
    """
    print(label, file=sys.stderr, flush=True)
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
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=wiki,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise Failure(f"could not run the maintainer — {exc}") from exc

    feeder = threading.Thread(target=_feed, args=(process.stdin, task), daemon=True)
    feeder.start()

    raw: list[str] = []
    events = others = 0
    result_text: str | None = None
    for line in iter(process.stdout.readline, ""):
        raw.append(line)
        event = _event(line.strip())
        if event is None:
            if line.strip():
                others += 1
            continue
        events += 1
        _announce_event(event)
        if event.get("type") == _RESULT:
            result_text = str(event.get("result", ""))
    process.stdout.close()
    feeder.join()
    code = process.wait()

    stdout = "".join(raw)
    streamed = events > 0 and others == 0
    product = result_text if streamed and result_text is not None else stdout
    return code, product


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
