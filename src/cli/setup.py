"""`setup` (SPEC-cli-008): doctor's own report, plus the printed remedy for
every required gap — and, under `--yes`, consent to run exactly those
commands and nothing else.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from . import doctor

CONFIG_NAME = "config.toml"
BREW_BOOTSTRAP = (
    '/bin/bash -c "$(curl -fsSL '
    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
)


def _remedy_table(home: Path) -> dict:
    path = home / CONFIG_NAME
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        config = {}
    table = (config.get("setup") or {}).get("remedy")
    return table if isinstance(table, dict) else {}


def _print_remedies(required_fail: list[dict], remedy: dict) -> list[str]:
    plan = []
    for row in required_fail:
        executable = row.get("executable")
        if executable is None:
            print(f"{row['check']}: {row['detail']} — no install fixes this")
            continue
        command = remedy.get(executable)
        if command is None:
            print(f"{executable}: missing, and tapedeck has no remedy for it")
            continue
        print(f"{executable}:\n    {command}")
        plan.append(command)
    return plan


def _print_optional(optional_rows: list[dict], remedy: dict) -> None:
    print("\noptional (never installed automatically):")
    for row in optional_rows:
        executable = row["executable"]
        command = remedy.get(executable)
        print(f"  {executable}: {command or row['detail']}")


def _model_note(rows: list[dict]) -> None:
    by_check = {r["check"]: r for r in rows}
    transcriber = by_check.get("transcribe.transcriber_command")
    if transcriber and transcriber["status"] == "pass":
        print("\nnote: the first transcription downloads the model.")


def cmd_setup(args, home: Path) -> int:
    print(f"library home: {home}")
    rows = doctor.checks(home)
    print(doctor.render_report(rows))

    remedy = _remedy_table(home)
    required_fail = [r for r in rows if r["status"] == "fail"]
    optional_gaps = [r for r in rows if r["status"] == "optional" and r.get("executable")]

    if not required_fail:
        print("\nready — nothing required is missing")
        if optional_gaps:
            _print_optional(optional_gaps, remedy)
        _model_note(rows)
        return 0

    print()
    plan = _print_remedies(required_fail, remedy)
    if optional_gaps:
        _print_optional(optional_gaps, remedy)

    needs_brew = any(command.strip().startswith("brew") for command in plan)
    brew_missing = needs_brew and shutil.which("brew") is None
    if brew_missing:
        print(
            "\nHomebrew is not installed, so the brew remedies above cannot run.\n"
            f"Install it first:\n    {BREW_BOOTSTRAP}"
        )

    if not args.yes:
        print("\nrun `tapedeck setup --yes` to apply the remedies above")
        return 1
    if brew_missing:
        return 1

    for command in plan:
        print(f"\n$ {command}", file=sys.stderr)
        subprocess.run(command, shell=True, env=os.environ)

    print()
    rows = doctor.checks(home)
    print(doctor.render_report(rows))
    if any(r["status"] == "fail" for r in rows):
        return 1
    print("\nready — nothing required is missing")
    _model_note(rows)
    return 0
