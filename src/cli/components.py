"""Driving the other components — always at their own boundary.

Each component is a program: `python -m ingest add <url>`, `python -m transcribe
run <id>`, and so on. The cli calls them that way rather than importing their
internals, because that is the boundary they are evaluated at and the boundary
they are replaceable at — a component rewritten in another language keeps this
caller working. (Their *vocabulary* is a different matter and is imported: see
library.py and LESSON-0003.)

Two rules hold for every call. The resolved home goes into the child's
environment, so a component never has to guess where the library is and its own
default can never be reached. And a child's stderr is inherited — progress from a
download or a transcription belongs on the user's terminal as it happens, not in
a buffer that appears when the work is already over.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Each component may be pointed somewhere else for a run — the same override the
# durable evaluations use to drive components in isolation.
COMMAND_VAR = "TAPEDECK_{}_CMD"


def command(module: str) -> list[str]:
    override = (os.environ.get(COMMAND_VAR.format(module.upper())) or "").strip()
    if override:
        return shlex.split(override)
    # sys.executable, not "python": the components are installed beside the cli,
    # in this interpreter's environment, and PATH may not agree about which
    # python that is.
    return [sys.executable, "-m", module]


def _env(home: Path) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home)}


def run(module: str, args: list[str], home: Path, quiet: bool = False) -> int:
    """Run one component and return its exit code.

    `quiet` swallows the child's stdout: inside a pipeline the paths each stage
    prints are its answer to its own caller, not this run's human output. Where
    the child's stdout *is* the answer — search results, an ask, a manual — it is
    inherited untouched, so nothing is buffered, reformatted or truncated on the
    way through.
    """
    result = subprocess.run(
        [*command(module), *args],
        env=_env(home),
        stdout=subprocess.DEVNULL if quiet else None,
    )
    return result.returncode


def capture(module: str, args: list[str], home: Path) -> tuple[int, str]:
    """Run one component and read its stdout — for the answers the cli acts on."""
    result = subprocess.run(
        [*command(module), *args],
        env=_env(home),
        stdout=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    return result.returncode, result.stdout or ""
