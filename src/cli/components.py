"""The seam to the other components: processes, not imports.

`python -m ingest add <url>` and friends — the same subprocess boundary each
component's own evaluations drive, so any of them can be swapped for another
implementation (or another language) without the cli noticing. Per component,
`$TAPEDECK_<NAME>_CMD` names a different command to run instead.

The cli stands in two relationships to a component, and they want different
plumbing. A read-only verb is *delegated*: the component's stdout is tapedeck's
stdout and its exit code is tapedeck's exit code. A pipeline *step* is driven:
the cli keeps the path the component printed and stops the pipeline if it fails.
Either way the component's stderr goes straight to the user — it explains its own
failures better than a wrapper could.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


class ComponentError(RuntimeError):
    """A component could not do what was asked; carries a process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def command(module: str) -> list[str]:
    override = os.environ.get(f"TAPEDECK_{module.upper()}_CMD")
    return shlex.split(override) if override else [sys.executable, "-m", module]


def _run(module: str, args: list[str], home: Path, capture: bool) -> tuple[int, str]:
    argv = [*command(module), *args]
    try:
        result = subprocess.run(
            argv,
            env={**os.environ, "TAPEDECK_HOME": str(home)},
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
    except OSError as exc:
        raise ComponentError(f"could not run the {module} component — {exc}") from exc
    # 2 is a component saying the request was wrong, and stays 2 all the way out.
    # Anything else — including a signal, which arrives negative — is a failure.
    code = 0 if result.returncode == 0 else (2 if result.returncode == 2 else 1)
    return code, (result.stdout or "").strip()


def delegate(module: str, args: list[str], home: Path) -> int:
    """Hand a verb over whole: the component's answer is tapedeck's answer."""
    return _run(module, args, home, capture=False)[0]


def step(module: str, args: list[str], home: Path) -> str:
    """Drive one step of a pipeline; return the path it printed, or stop."""
    code, out = _run(module, args, home, capture=True)
    if code:
        raise ComponentError(f"the {module} step failed", code)
    return out
