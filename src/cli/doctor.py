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

Every check is reported, passes included, because a diagnosis that prints only
complaints cannot tell "checked and fine" from "never looked".
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

# The seams, in the order the report emits them; the flag is whether `add` needs
# it. `ask` needs the last two and `search` never does, so they are optional and
# never decide the exit code.
SEAMS = (
    ("ingest", "fetcher_command", True),
    ("ingest", "lister_command", True),
    ("transcribe", "transcriber_command", True),
    ("ask", "librarian_command", False),
    ("ask", "answerer_command", False),
)
COSTS = "ask needs it, search does not"
# Transcribers that exist only for Apple Silicon. Named here because the platform
# check is about the silicon, not about the tool: any other transcriber is
# portable and this check has nothing to say about it.
MLX_TOOLS = ("mlx_whisper", "parakeet-mlx")


def row(check: str, status: str, detail: str) -> dict:
    return {"check": check, "status": status, "detail": detail}


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


def head(command: str) -> str:
    """The head executable of a command template: its first shell word. A template
    built from pipeline or `&&` stages has more heads than this; the first one is
    the one that always has to resolve, because nothing else runs without it."""
    try:
        words = shlex.split(command)
    except ValueError:  # unbalanced quoting — the shell would not run it either
        words = command.split()
    return words[0] if words else ""


def seam_row(settings: dict, section: str, key: str, required: bool, unreadable) -> dict:
    check = f"{section}.{key}"
    bad = FAIL if required else OPTIONAL
    table = settings.get(section)
    command = table.get(key) if isinstance(table, dict) else None
    if not isinstance(command, str) or not command.strip():
        why = "nothing for `add` to run" if required else COSTS
        return row(check, bad, f"{unreadable or f'not set in {CONFIG_NAME}'} — {why}")
    name = head(command.strip())
    found = shutil.which(name) if name else None
    if found:
        return row(check, PASS, f"{name} at {found}")
    detail = f"{name}: not on PATH"
    return row(check, bad, detail if required else f"{detail} — {COSTS}")


def ffmpeg_row() -> dict:
    found = shutil.which("ffmpeg")
    if found:
        return row("ffmpeg", PASS, f"ffmpeg at {found}")
    return row(
        "ffmpeg",
        FAIL,
        "ffmpeg: not on PATH — the downloader merges the separate video and "
        "audio streams with it",
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
    transcribe = settings.get("transcribe")
    command = transcribe.get("transcriber_command") if isinstance(transcribe, dict) else None
    rows += [
        ffmpeg_row(),
        home_row(home),
        fts5_row(),
        platform_row(command if isinstance(command, str) else ""),
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


def run(home: Path, as_json: bool) -> int:
    rows = diagnose(home)
    # No escape sequences, ever: this output is read by pipes and by `--json`
    # consumers as often as by people (SPEC-cli-005).
    print(json.dumps(rows, ensure_ascii=False, indent=2) if as_json else report(rows))
    failed = [item["check"] for item in rows if item["status"] == FAIL]
    if failed:
        print(f"{len(failed)} check(s) failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0
