"""Running the components — one boundary, the same one their own evals drive.

Each component is `python -m <name>` with the library resolved from
`$TAPEDECK_HOME`. The interpreter is this one (`sys.executable`), so tapedeck runs
the components installed beside it rather than whatever `python` means on the
user's PATH today. `$TAPEDECK_<NAME>_CMD` replaces one, the same escape hatch the
durable evaluations use to drive a component that is not a Python module.

Three ways to run one, because a component's stdout means three different things
to the cli:

- `passthrough` — its answer is ours (`search`, `ask`, `reindex`, the parakeet
  filter): stdin, stdout and stderr are inherited untouched, and its exit code
  becomes ours.
- `capture` — its answer is our input (`ingest expand`), so stdout is read.
- `quietly` — a step in a pipeline, where the path it prints is progress and the
  cli's own stdout carries the summary: stdout is redirected to stderr, the way
  ingest treats a fetcher's chatter.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

STDERR_FD = 2


class Usage(ValueError):
    """The request cannot be acted on as it stands — exit 2."""


class Failed(RuntimeError):
    """The operation was attempted and did not complete — exit 1."""


def command(module: str) -> list[str]:
    override = os.environ.get(f"TAPEDECK_{module.upper()}_CMD")
    return shlex.split(override) if override else [sys.executable, "-m", module]


def _env(home: Path) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home)}


def passthrough(home: Path, module: str, args: list[str]) -> int:
    """Hand the terminal over: the component's streams are the cli's."""
    return subprocess.run([*command(module), *args], env=_env(home)).returncode


def quietly(home: Path, module: str, args: list[str]) -> int:
    """Run a pipeline step. Its stdout is progress and goes to stderr with it."""
    return subprocess.run(
        [*command(module), *args], env=_env(home), stdout=STDERR_FD
    ).returncode


def capture(home: Path, module: str, args: list[str]) -> tuple[int, str]:
    """Run a component for what it prints. stderr still reaches the user."""
    result = subprocess.run(
        [*command(module), *args],
        env=_env(home),
        stdout=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    return result.returncode, result.stdout or ""


def step(home: Path, module: str, args: list[str], video_id: str) -> None:
    """One link of the derivation chain. Anything but a clean exit stops this
    video — deriving an archive page from a transcript that was never written
    would only turn one failure into two."""
    code = quietly(home, module, args)
    if code:
        raise Failed(f"{video_id}: {module} {args[0]} failed (exit {code})")
