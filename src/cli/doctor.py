"""`doctor` (SPEC-cli-007) and the check machinery `setup` reuses verbatim
(SPEC-cli-008): one report, two verbs, so a check added here appears in
`setup` with no code there.
"""

from __future__ import annotations

import json
import os
import platform as platform_module
import re
import shlex
import shutil
import sqlite3
import sys
import tomllib
from pathlib import Path

CONFIG_NAME = "config.toml"
REQUIRED = "required"
OPTIONAL = "optional"

# SPEC-cli-007's fixed order: the seams by dotted config key, then what the
# derivation chain needs whatever tools fill it.
SEAMS = (
    ("ingest.fetcher_command", "ingest", "fetcher_command", REQUIRED, None),
    ("ingest.lister_command", "ingest", "lister_command", REQUIRED, None),
    ("transcribe.transcriber_command", "transcribe", "transcriber_command", REQUIRED, None),
    ("ask.librarian_command", "ask", "librarian_command", OPTIONAL, "ask needs it, search does not"),
    ("ask.answerer_command", "ask", "answerer_command", OPTIONAL, "ask --fast needs it, search does not"),
    (
        "wiki.maintainer_command",
        "wiki",
        "maintainer_command",
        OPTIONAL,
        "the wiki verbs that write and add's auto-filing epilogue need it, lint does not",
    ),
)

MLX_TOOLS = ("mlx_whisper", "parakeet-mlx")
# `VAR=value cmd` sets VAR for cmd; the head is the first word that isn't one
# of these assignments (SPEC-cli-010).
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _load_config(home: Path) -> dict:
    path = home / CONFIG_NAME
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}


def head(command: str) -> str | None:
    """The first shell word that is not a `NAME=value` assignment."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for token in tokens:
        if not ASSIGNMENT.match(token):
            return token
    return None


def _seam_row(name, section, key, kind, reason, config) -> dict:
    value = (config.get(section) or {}).get(key)
    unresolved_status = OPTIONAL if kind == OPTIONAL else "fail"
    if not isinstance(value, str) or not value.strip():
        detail = f"not configured — add [{section}] {key} to config.toml"
        if reason:
            detail += f" ({reason})"
        return {"check": name, "status": unresolved_status, "detail": detail, "executable": None}
    program = head(value.strip())
    if program is None:
        return {
            "check": name,
            "status": unresolved_status,
            "detail": f"{value.strip()!r} names no program",
            "executable": None,
        }
    resolved = shutil.which(program)
    if resolved:
        return {
            "check": name,
            "status": "pass",
            "detail": f"{program} — resolves on PATH",
            "executable": program,
        }
    detail = f"{program}: not on PATH"
    if reason and kind == OPTIONAL:
        detail += f" — {reason}"
    return {"check": name, "status": unresolved_status, "detail": detail, "executable": program}


def _ffmpeg_row() -> dict:
    resolved = shutil.which("ffmpeg")
    if resolved:
        return {
            "check": "ffmpeg",
            "status": "pass",
            "detail": "ffmpeg — resolves on PATH",
            "executable": "ffmpeg",
        }
    return {"check": "ffmpeg", "status": "fail", "detail": "ffmpeg: not on PATH", "executable": "ffmpeg"}


def _home_row(home: Path) -> dict:
    if not home.is_dir():
        return {"check": "home", "status": "fail", "detail": f"{home} does not exist", "executable": None}
    if not os.access(home, os.W_OK):
        return {"check": "home", "status": "fail", "detail": f"{home} is not writable", "executable": None}
    return {"check": "home", "status": "pass", "detail": f"{home} — resolved and writable", "executable": None}


def _fts5_row() -> dict:
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        return {
            "check": "fts5",
            "status": "fail",
            "detail": f"SQLite FTS5 is not available in this python — {exc}",
            "executable": None,
        }
    return {"check": "fts5", "status": "pass", "detail": "available", "executable": None}


def _platform_row(config: dict) -> dict:
    section = config.get("transcribe") or {}
    command = section.get("transcriber_command")
    program = head(command.strip()) if isinstance(command, str) and command.strip() else None
    if program not in MLX_TOOLS:
        return {
            "check": "platform",
            "status": "pass",
            "detail": "the configured transcriber is not Apple-Silicon-only",
            "executable": None,
        }
    apple_silicon = sys.platform == "darwin" and platform_module.machine() == "arm64"
    if apple_silicon:
        return {
            "check": "platform",
            "status": "pass",
            "detail": f"{program} needs Apple Silicon macOS — this machine qualifies",
            "executable": None,
        }
    detail = (
        f"{program} needs Apple Silicon macOS ({sys.platform}/{platform_module.machine()} "
        "will not run it) — point [transcribe] transcriber_command in config.toml at a "
        "transcriber that runs here"
    )
    return {"check": "platform", "status": "fail", "detail": detail, "executable": None}


def checks(home: Path) -> list[dict]:
    config = _load_config(home)
    rows = [_seam_row(name, section, key, kind, reason, config) for name, section, key, kind, reason in SEAMS]
    rows.append(_ffmpeg_row())
    rows.append(_home_row(home))
    rows.append(_fts5_row())
    rows.append(_platform_row(config))
    return rows


def public(rows: list[dict]) -> list[dict]:
    return [{"check": r["check"], "status": r["status"], "detail": r["detail"]} for r in rows]


def render_report(rows: list[dict]) -> str:
    name_width = max(len(r["check"]) for r in rows)
    status_width = max(len(r["status"]) for r in rows)
    return "\n".join(
        f"{r['check'].ljust(name_width)}  {r['status'].ljust(status_width)}  {r['detail']}" for r in rows
    )


def failures(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] == "fail"]


def cmd_doctor(args, home: Path) -> int:
    rows = checks(home)
    if args.json:
        print(json.dumps(public(rows), ensure_ascii=False, indent=2))
    else:
        print(render_report(rows))
    return 1 if failures(rows) else 0
