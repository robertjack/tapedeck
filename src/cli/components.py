"""Running the components — the cli's only way to reach them.

Each component is driven at exactly the boundary its own evaluations use:
`python -m <component> …`, overridable per component with $TAPEDECK_<NAME>_CMD.
So the cli composes verbs without importing a single line of another component,
and any of them can be regenerated — or swapped for something else entirely —
underneath it.

Whose stdout is the user's stdout is decided per call. A pass-through verb
(`search`, `ask`, `reindex`) hands the component the terminal and the component's
answer *is* the answer; inside the `add` pipeline every step is captured and
echoed to stderr, so a four-process pipeline still prints one line of stdout.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys


class RunError(RuntimeError):
    """A component could not be run at all (as opposed to running and failing)."""


def override(module: str) -> str | None:
    return os.environ.get(f"TAPEDECK_{module.upper()}_CMD")


def invocation(module: str) -> list[str]:
    command = override(module)
    if command:
        return shlex.split(command)
    if importlib.util.find_spec(module) is None:
        raise RunError(f"the {module} component is not installed — nothing at `-m {module}`")
    # sys.executable, not `python`: the components live wherever tapedeck does.
    return [sys.executable, "-m", module]


def run(module: str, args: list[str], home, capture: bool = False) -> tuple[int, str]:
    """Run one component verb against `home`. Returns (exit code, stdout)."""
    argv = [*invocation(module), *args]
    env = {**os.environ, "TAPEDECK_HOME": str(home)}
    try:
        result = subprocess.run(
            argv, env=env, text=True, stdout=subprocess.PIPE if capture else None
        )
    except OSError as exc:
        raise RunError(f"could not run the {module} component — {exc}") from exc
    out = result.stdout or ""
    if out:
        # Captured output is still the component talking: it becomes progress
        # rather than disappearing.
        sys.stderr.write(out if out.endswith("\n") else out + "\n")
    return result.returncode, out
