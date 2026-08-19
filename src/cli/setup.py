"""`setup`: the first-verb wizard, and its `--refresh` sibling (SPEC-cli-008,
SPEC-cli-013).

Consent is the specification: nothing runs without `--yes`, and `--yes` runs
only the commands this run already printed. `setup` reports exactly what
`doctor` reports — same function, same rows — and adds only the remedy (or
update) column beside a failing (or resolving) check.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from . import doctor

TRANSCRIBER_CHECK = "transcribe.transcriber_command"
BREW_BOOTSTRAP = "Homebrew is missing — install it first: https://brew.sh"


def _setup_table(home: Path, key: str) -> dict:
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    table = (config.get("setup") or {}).get(key)
    return table if isinstance(table, dict) else {}


def _needs_homebrew(commands: list[str]) -> bool:
    return any(cmd.strip().startswith("brew") for cmd in commands) and shutil.which("brew") is None


def _download_note(rows: list) -> None:
    transcriber = next((c for c in rows if c.check == TRANSCRIBER_CHECK), None)
    if transcriber and transcriber.status != "fail":
        print(
            "note: the first transcription downloads the model — this can "
            "take a while and a few GB of disk"
        )


def run(home: Path, yes: bool, refresh: bool) -> int:
    print(f"tapedeck home: {home}")
    if refresh:
        return _refresh(home, yes)
    return _plain(home, yes)


def _plain(home: Path, yes: bool) -> int:
    rows = doctor.checks(home)
    print(doctor.format_report(rows))
    required_fail = [c for c in rows if c.status == "fail"]

    remedy_table = _setup_table(home, "remedy")
    remedies: list[str] = []
    unknown: list[str] = []
    for check in required_fail:
        if check.executable is None:
            print(f"{check.check}: {check.detail} — no install fixes this", file=sys.stderr)
            continue
        command = remedy_table.get(check.executable)
        (remedies if command else unknown).append(command or check.executable)

    if _needs_homebrew(remedies):
        print(BREW_BOOTSTRAP)
    for command in remedies:
        print(command)
    for executable in unknown:
        print(f"no remedy known for {executable} — install it yourself", file=sys.stderr)

    _download_note(rows)

    if not required_fail:
        print("tapedeck is ready.")
        return 0
    if not yes or _needs_homebrew(remedies):
        return 1

    for command in remedies:
        subprocess.run(command, shell=True)
    print()
    rows2 = doctor.checks(home)
    print(doctor.format_report(rows2))
    if not any(c.status == "fail" for c in rows2):
        print("tapedeck is ready.")
        return 0
    return 1


def _refresh(home: Path, yes: bool) -> int:
    rows = doctor.checks(home)
    print(doctor.format_report(rows))
    update_table = _setup_table(home, "update")
    commands = []
    for check in rows:
        if check.status == "fail" or check.executable is None:
            continue
        command = update_table.get(check.executable)
        if command:
            print(command)
            commands.append(command)

    if not yes or not commands:
        return 0
    for command in commands:
        subprocess.run(command, shell=True)
    print()
    rows2 = doctor.checks(home)
    print(doctor.format_report(rows2))
    return 1 if any(c.status == "fail" for c in rows2) else 0
