"""`doctor`: read-only diagnosis, derived from the config seams (SPEC-cli-007).

`checks()` is the one implementation `setup` also reports through (SPEC-cli-008)
— a check added here appears there with no code of its own. Nothing here runs a
seam command: a head executable is resolved on PATH, never executed.
"""

from __future__ import annotations

import json
import os
import platform as platform_mod
import re
import shlex
import shutil
import sqlite3
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
MLX_TOOLS = {"mlx_whisper", "parakeet-mlx"}

# (section, key, required) in the pinned order (SPEC-cli-007).
SEAM_CHECKS = (
    ("ingest", "fetcher_command", True),
    ("ingest", "lister_command", True),
    ("transcribe", "transcriber_command", True),
    ("ask", "librarian_command", False),
    ("ask", "answerer_command", False),
    ("wiki", "maintainer_command", False),
)

COST_NOTE = {
    "ask": "optional — needed by `ask`, never by `search`",
    "wiki": "optional — costs the `wiki` verbs that write, and `add`'s auto-filing epilogue",
}

NAME_WIDTH = max(len(f"{section}.{key}") for section, key, _ in SEAM_CHECKS)


@dataclass
class Check:
    check: str
    status: str
    detail: str
    executable: str | None = None

    def row(self) -> dict:
        return {"check": self.check, "status": self.status, "detail": self.detail}


def _config(home: Path) -> dict:
    path = home / "config.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}


def _head(command: str) -> str | None:
    """The program a shell would run: the first word that is not a
    `NAME=value` assignment (SPEC-cli-010)."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    for word in words:
        if not ASSIGNMENT.match(word):
            return word
    return None


def _seam_check(config: dict, section: str, key: str, required: bool) -> Check:
    name = f"{section}.{key}"
    value = (config.get(section) or {}).get(key)
    configured = isinstance(value, str) and bool(value.strip())
    head = _head(value.strip()) if configured else None
    if configured and head and shutil.which(head):
        return Check(name, "pass", f"{head}: found on PATH", executable=head)
    if not configured:
        base, exe = f"not configured — set [{section}] {key} in config.toml", None
    else:
        exe = head or value.strip()
        base = f"{exe}: not on PATH"
    if required:
        return Check(name, "fail", base, executable=exe)
    return Check(name, "optional", f"{base} ({COST_NOTE[section]})", executable=exe)


def _ffmpeg_check() -> Check:
    if shutil.which("ffmpeg"):
        return Check("ffmpeg", "pass", "ffmpeg: found on PATH", executable="ffmpeg")
    return Check("ffmpeg", "fail", "ffmpeg: not on PATH", executable="ffmpeg")


def _home_check(home: Path) -> Check:
    try:
        home.mkdir(parents=True, exist_ok=True)
        ok = os.access(home, os.W_OK)
    except OSError:
        ok = False
    return Check("home", "pass" if ok else "fail", str(home) if ok else f"{home} is not writable")


def _fts5_check() -> Check:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        conn.close()
        return Check("fts5", "pass", "SQLite FTS5 is available in this python")
    except sqlite3.Error as exc:
        return Check("fts5", "fail", f"SQLite FTS5 is not available — {exc}")


def _platform_check(config: dict) -> Check:
    command = (config.get("transcribe") or {}).get("transcriber_command")
    head = _head(command.strip()) if isinstance(command, str) and command.strip() else None
    if head not in MLX_TOOLS:
        return Check("platform", "pass", "the configured transcriber is not Apple-Silicon-only")
    if sys.platform == "darwin" and platform_mod.machine() == "arm64":
        return Check("platform", "pass", f"{head} needs Apple Silicon, and this machine is one")
    return Check(
        "platform",
        "fail",
        f"{head} needs Apple Silicon macOS — set [transcribe] transcriber_command "
        "in config.toml to a transcriber that runs here",
    )


def checks(home: Path) -> list[Check]:
    config = _config(home)
    rows = [_seam_check(config, section, key, required) for section, key, required in SEAM_CHECKS]
    rows += [_ffmpeg_check(), _home_check(home), _fts5_check(), _platform_check(config)]
    return rows


def format_report(rows: list[Check]) -> str:
    return "\n".join(
        f"{c.check.ljust(NAME_WIDTH)}  {c.status.ljust(8)} {c.detail}" for c in rows
    )


def report_json(rows: list[Check]) -> str:
    return json.dumps([c.row() for c in rows], ensure_ascii=False, indent=2)


def run(home: Path, as_json: bool) -> int:
    rows = checks(home)
    print(report_json(rows) if as_json else format_report(rows))
    return 1 if any(c.status == "fail" for c in rows) else 0
