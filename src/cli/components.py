"""The other components, reached where their own evaluations reach them.

Each one is a program — `python -m ingest add <url>`, `python -m archive render
<id>` — and the cli composes them across process boundaries rather than importing
their behaviour. A component can then be regenerated in another language without
the orchestrator noticing, and a step that dies takes only its own process down.
(Vocabulary is the exception and is imported, never re-derived: see library.py.)

stdout is a component's answer. For the links of the derivation chain it is
captured, because `tapedeck add` reports what happened rather than four paths; for
the verbs the cli merely routes — search, ask, reindex, adapt-parakeet — the child
writes straight to ours, so results and stdin stream untouched. stderr is progress
either way and is never captured.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

INGEST, TRANSCRIBE, ARCHIVE, INDEX, ASK = "ingest", "transcribe", "archive", "index", "ask"


def command(module: str) -> list[str]:
    """How to run one component: this interpreter — the one tapedeck was installed
    into, whatever python happens to be on PATH — unless an environment override
    names something else, which is the seam the eval harness drives."""
    override = os.environ.get(f"TAPEDECK_{module.upper()}_CMD")
    return shlex.split(override) if override else [sys.executable, "-m", module]


def run(module: str, args: list[str], home: Path, capture: bool = False):
    # Our own lines are buffered when stdout is a pipe; the child's are not. Flush
    # first or a summary printed before a forwarded verb lands after it.
    sys.stdout.flush()
    return subprocess.run(
        [*command(module), *args],
        env={**os.environ, "TAPEDECK_HOME": str(home)},
        stdout=subprocess.PIPE if capture else None,
        text=True,
    )


def step(module: str, args: list[str], home: Path) -> int:
    """One link of the chain: its exit code kept, its stdout swallowed."""
    return run(module, args, home, capture=True).returncode


def output(module: str, args: list[str], home: Path) -> tuple[int, str]:
    """A component asked a question — exit code and what it said."""
    result = run(module, args, home, capture=True)
    return result.returncode, result.stdout or ""


def forward(module: str, args: list[str], home: Path) -> int:
    """A verb the cli only routes: the component's stdout is the user's answer."""
    return run(module, args, home).returncode
