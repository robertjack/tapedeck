"""Delegating to the components — each one a process, never an import.

`python -m ingest add <url>` is the same boundary ingest's own evaluations
drive, so the cli depends on what a component does and what it exits with, and
on nothing about how it is written: any component can be regenerated whole
without touching this file (SPEC-core-002). $TAPEDECK_<NAME>_CMD overrides a
component the way the harness does, which is also how a replacement
implementation gets tried without reinstalling anything.

The home is named to every child explicitly, so a child can never resolve a
different library than the run that called it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import Failure


@dataclass(frozen=True)
class Result:
    code: int
    stdout: str = ""


def command(module: str) -> list[str]:
    override = os.environ.get(f"TAPEDECK_{module.upper()}_CMD", "").strip()
    # sys.executable, not `python`: the interpreter running tapedeck is the one
    # the components are installed beside.
    return shlex.split(override) if override else [sys.executable, "-m", module]


def run(module: str, args: list[str], home: Path, capture: bool = False) -> Result:
    """Run a component verb. `capture` keeps the component's stdout out of ours —
    intermediate artifact paths are the pipeline's business, not the user's —
    while stderr always passes straight through, because progress is theirs to
    narrate and diagnostics are the user's to see."""
    argv = [*command(module), *args]
    env = {**os.environ, "TAPEDECK_HOME": str(home)}
    sys.stdout.flush()  # children write to fd 1 directly; keep the order honest
    try:
        done = subprocess.run(
            argv, env=env, text=True, stdout=subprocess.PIPE if capture else None
        )
    except OSError as exc:
        raise Failure(f"could not run `{shlex.join(argv)}` — {exc}") from exc
    return Result(exit_code(done.returncode), done.stdout or "")


def exit_code(code: int) -> int:
    """Only 0, 1 and 2 mean anything at this boundary (contracts/cli-surface.md).
    A component killed by a signal, or exiting with something else, is an
    operation failure — not a usage error the user could fix by retyping."""
    return code if code in (0, 1, 2) else 1
