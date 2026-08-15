"""`doctor` — a diagnosis of this installation, for the moment `add` failed and
the user cannot tell whether the fault is theirs, the machine's, or tapedeck's.

It changes nothing, touches the network never, and runs none of the tools it asks
about: it resolves names on `PATH`, it does not execute what it finds. A broken
seam is exactly when you want to ask about it, and rehearsing it is how a
diagnosis becomes an incident.

The checks are derived from the configuration seams (SPEC-cli-007), never from a
list of tools kept here. tapedeck has no opinion about which downloader or
transcriber a user runs (SPEC-core-004), so doctor may not have one either: it
takes each command template in config.toml, takes its head executable — the first
shell word — and looks for that name. Point `transcriber_command` somewhere else
and doctor starts checking for somewhere else, with no change to this file.

Required means `add` cannot run without it. The `[ask]` seams and the `[wiki]`
maintainer are optional on the same footing, and each says which half of the tool
its absence costs: `ask` needs the librarian and `search` never does; the wiki's
writing verbs and `add`'s filing epilogue need the maintainer and the four-stage
chain never does. Neither ever decides the exit code.

Every check is reported, passes included, because a diagnosis that prints only
complaints cannot tell "checked and fine" from "never looked".

This module is also where `setup` gets its diagnosis (SPEC-cli-008), which is why
a row carries one thing the report never prints: `missing`, the executable that
could not be found. The wizard needs the name to look up a remedy, and deriving
it a second time over there is exactly the drift LESSON-0003 is about.
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import sqlite3
import sys
import tomllib
from contextlib import closing
from pathlib import Path

from .home import CONFIG_NAME

PASS, FAIL, OPTIONAL = "pass", "fail", "optional"
# What a check is, on the wire and in the report: everything else on a row is
# ours (system/contracts/cli-surface.md pins `--json` to these three).
PUBLIC = ("check", "status", "detail")

# What an optional seam's absence costs. Required seams carry no such line
# because there is nothing to weigh: without them `add` has nothing to run.
REQUIRED = None
ASK_COSTS = "ask needs it, search does not"
WIKI_COSTS = (
    "the wiki verbs that write need it, and so does the filing `add` does after "
    "each video; the four-stage chain never does"
)

# The seams, in the order the report emits them.
SEAMS = (
    ("ingest", "fetcher_command", REQUIRED),
    ("ingest", "lister_command", REQUIRED),
    ("transcribe", "transcriber_command", REQUIRED),
    ("ask", "librarian_command", ASK_COSTS),
    ("ask", "answerer_command", ASK_COSTS),
    ("wiki", "maintainer_command", WIKI_COSTS),
)
TRANSCRIBER = ("transcribe", "transcriber_command")
# Transcribers that exist only for Apple Silicon. Named here because the platform
# check is about the silicon, not about the tool: any other transcriber is
# portable and this check has nothing to say about it.
MLX_TOOLS = ("mlx_whisper", "parakeet-mlx")


def row(check: str, status: str, detail: str, missing: str | None = None) -> dict:
    return {"check": check, "status": status, "detail": detail, "missing": missing}


def public(rows: list[dict]) -> list[dict]:
    """The rows as the surface promises them: check, status, detail, nothing else."""
    return [{key: item[key] for key in PUBLIC} for item in rows]


def config(home: Path) -> tuple[dict, str | None]:
    """config.toml as data, or the reason it could not be read. Unreadable is not
    a crash here: "your config is not valid TOML" is a diagnosis too."""
    path = home / CONFIG_NAME
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return {}, f"no {path}"
    except (OSError, ValueError) as exc:
        return {}, f"{path} could not be read — {exc}"


def setting(settings: dict, section: str, key: str) -> str:
    """One seam's command template, or "" if this config does not set it."""
    table = settings.get(section)
    command = table.get(key) if isinstance(table, dict) else None
    return command.strip() if isinstance(command, str) else ""


def head(command: str) -> str:
    """The head executable of a command template: its first shell word. A template
    built from pipeline or `&&` stages has more heads than this; the first one is
    the one that always has to resolve, because nothing else runs without it."""
    try:
        words = shlex.split(command)
    except ValueError:  # unbalanced quoting — the shell would not run it either
        words = command.split()
    return words[0] if words else ""


def seam_row(settings: dict, section: str, key: str, costs: str | None, unreadable) -> dict:
    check = f"{section}.{key}"
    required = costs is REQUIRED
    bad = FAIL if required else OPTIONAL
    command = setting(settings, section, key)
    if not command:
        why = "nothing for `add` to run" if required else costs
        return row(check, bad, f"{unreadable or f'not set in {CONFIG_NAME}'} — {why}")
    name = head(command)
    if name and shutil.which(name):
        # The name that resolved, not the path it resolved to: which prefix a
        # tool happens to sit in is noise in a diagnosis, and a column of
        # absolute paths is a column nobody skims.
        return row(check, PASS, f"{name} on PATH")
    detail = f"{name}: not on PATH"
    return row(check, bad, detail if required else f"{detail} — {costs}", missing=name)


def ffmpeg_row() -> dict:
    if shutil.which("ffmpeg"):
        return row("ffmpeg", PASS, "ffmpeg on PATH")
    return row(
        "ffmpeg",
        FAIL,
        "ffmpeg: not on PATH — the downloader merges the separate video and "
        "audio streams with it",
        missing="ffmpeg",
    )


def home_row(home: Path) -> dict:
    if not home.is_dir():
        return row("home", FAIL, f"{home}: the library home is not a directory")
    if not os.access(home, os.W_OK):
        return row("home", FAIL, f"{home}: the library home is not writable")
    return row("home", PASS, f"{home} (writable)")


def fts5_row() -> dict:
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
    except sqlite3.Error as exc:
        return row(
            "fts5",
            FAIL,
            f"this python's sqlite3 has no FTS5 ({exc}) — without it there is no index",
        )
    return row("fts5", PASS, f"SQLite {sqlite3.sqlite_version} with FTS5")


def platform_row(transcriber: str) -> dict:
    machine = platform.machine()
    here = f"{sys.platform}/{machine}"
    apple_silicon = sys.platform == "darwin" and machine == "arm64"
    tool = next((name for name in MLX_TOOLS if name in transcriber), None)
    if tool and not apple_silicon:
        return row(
            "platform",
            FAIL,
            f"{tool} is MLX, and MLX needs Apple Silicon (arm64 macOS); this is "
            f"{here} — [transcribe] transcriber_command in {CONFIG_NAME} is one "
            "line away from a transcriber that runs here",
        )
    if tool:
        return row("platform", PASS, f"{here} runs {tool}")
    return row("platform", PASS, f"{here}; the configured transcriber is portable")


def diagnose(home: Path) -> list[dict]:
    """Every check, always, in the order SPEC-cli-007 pins."""
    settings, unreadable = config(home)
    rows = [seam_row(settings, *seam, unreadable) for seam in SEAMS]
    rows += [
        ffmpeg_row(),
        home_row(home),
        fts5_row(),
        platform_row(setting(settings, *TRANSCRIBER)),
    ]
    return rows


def report(rows: list[dict]) -> str:
    """One aligned line per check, so the statuses skim as a column."""
    width = max(len(item["check"]) for item in rows)
    status = max(len(item["status"]) for item in rows)
    return "\n".join(
        f"{item['check']:<{width}}  {item['status']:<{status}}  {item['detail']}"
        for item in rows
    )


def failed(rows: list[dict]) -> list[dict]:
    """The required checks that did not pass — the only thing that decides an
    exit code, here and in `setup`. Optional results never make it 1."""
    return [item for item in rows if item["status"] == FAIL]


def run(home: Path, as_json: bool) -> int:
    rows = diagnose(home)
    # No escape sequences, ever: this output is read by pipes and by `--json`
    # consumers as often as by people (SPEC-cli-005).
    print(json.dumps(public(rows), ensure_ascii=False, indent=2) if as_json else report(rows))
    broken = [item["check"] for item in failed(rows)]
    if broken:
        print(f"{len(broken)} check(s) failed: {', '.join(broken)}", file=sys.stderr)
    return 1 if broken else 0
