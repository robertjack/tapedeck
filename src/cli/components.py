"""How the cli talks to the components that own the library's paths.

Each component is a module CLI — `python -m ingest add`, `python -m transcribe
run`, `python -m archive render`, `python -m index update`, `python -m ask run` —
and the cli drives exactly that boundary, the same one each component's own
durable evaluations use. Nothing here reaches past it into an internal the
component never promised to keep.

The resolved home travels in the environment because the cli is the sole
authority on where the library is (SPEC-cli-001); a child left to work out its
own default could find a different one.

Three ways to run a child, and the difference is whose answer stdout carries.
A `stage` is one link of the derivation chain: its stdout is the path it just
wrote — progress, not the answer — so it is folded into our stderr, leaving
`add`'s stdout for the summary alone. `passthrough` is for the read-only verbs
the cli delegates whole; there the component's stdout *is* the answer and its
exit code is ours. `capture` is for the one case where the cli reads a
component's output itself: the ids in a collection.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

STDERR_FD = 2


def _argv(module: str, args) -> list[str]:
    # This interpreter, so the components found are the ones installed beside us.
    return [sys.executable, "-m", module, *args]


def _env(home: Path) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home)}


def stage(module: str, args, home: Path) -> int:
    """One link of the chain. Its stdout joins our diagnostics on stderr."""
    sys.stderr.flush()
    return subprocess.run(_argv(module, args), env=_env(home), stdout=STDERR_FD).returncode


def passthrough(module: str, args, home: Path) -> int:
    """Hand the verb over whole: the child's stdio is ours, and so is its exit."""
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(_argv(module, args), env=_env(home)).returncode


def capture(module: str, args, home: Path) -> tuple[int, str]:
    """Run a component for its output. Its stderr still reaches the user."""
    sys.stderr.flush()
    result = subprocess.run(
        _argv(module, args), env=_env(home), stdout=subprocess.PIPE, text=True, errors="replace"
    )
    return result.returncode, result.stdout or ""
