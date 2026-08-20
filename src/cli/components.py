"""How the cli reaches every sibling component, and the wiki filing epilogue.

Two shapes of call, both `python -m <module>` under the same interpreter this
process is running (`sys.executable`, so no assumption about which python is
on PATH): `run_module` for a pipeline stage, whose stdout is captured (the
cli only needs its exit code) while stderr is inherited (so live progress —
ingest's fetch heartbeat, transcribe's model line — reaches the user as it
happens); `run_passthrough` for a verb handed over whole (search, ask,
reindex, wiki — SPEC-cli-009's routing rule), whose streams are both
inherited so the child's exact bytes are the user's.

The wiki auto-filing epilogue (SPEC-cli-009, detached per SPEC-cli-011) lives
here too: `add` hands it the ids that just completed, and everything about
whether and how they get filed is decided from that one call.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import wiki as wiki_pkg
from wiki import seams as wiki_seams

WORKER_ARG = "_wiki_worker"


def _env(home: Path) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home)}


def run_module(home: Path, module: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        env=_env(home),
        stdout=subprocess.PIPE,
        text=True,
    )


def run_passthrough(home: Path, module: str, args: list[str]) -> int:
    return subprocess.run([sys.executable, "-m", module, *args], env=_env(home)).returncode


def wiki_auto_enabled(home: Path) -> bool:
    """`[wiki].auto` gates the epilogue, and an ABSENT key reads false
    (SPEC-cli-009, amended for the public era): a filing spends real money on
    the account `maintainer_command` names, and a stranger's first `add` must
    never spend it unasked. One default, written into the scaffold as
    `auto = false`, and this function agrees with what it wrote — only an
    explicit `auto = true` turns the epilogue on."""
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    section = config.get("wiki")
    if not isinstance(section, dict) or "auto" not in section:
        return False
    return bool(section["auto"])


def spawn_wiki_worker(home: Path, ids: list[str]) -> None:
    """One detached process per `add` invocation (SPEC-cli-011): it outlives
    `add` and holds none of its streams — stdio is fully redirected away, and
    a new session keeps it out of add's own process group."""
    subprocess.Popen(
        [sys.executable, "-m", "cli", WORKER_ARG, *ids],
        env=_env(home),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wiki_worker_main(home: Path, ids: list[str]) -> None:
    """The worker itself: files each id in the sweep's own completion order,
    at the component boundary (`wiki file --wait <id>`, SPEC-wiki-012), one
    at a time so a later filing can read pages an earlier one just wrote
    (SPEC-wiki-003's accumulation). Both streams are discarded — nobody is
    at a terminal to read them; the wiki's own log is the record."""
    for video_id in ids:
        subprocess.run(
            [sys.executable, "-m", "wiki", "file", "--wait", video_id],
            env=_env(home),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def wiki_epilogue(home: Path, filed_ids: list[str]) -> None:
    """Best-effort, and that is the specification (SPEC-cli-009): a filing
    that cannot happen costs nothing but itself. What `add` can know before
    the hand-off is settled synchronously; everything after belongs to the
    detached worker and is never awaited."""
    if not filed_ids or not wiki_auto_enabled(home):
        return
    try:
        wiki_seams.maintainer_command(home)
    except wiki_pkg.Usage:
        print(
            "note: [wiki].maintainer_command is not configured — add will "
            "not file the wiki this run (see `tapedeck doctor`)",
            file=sys.stderr,
        )
        return
    spawn_wiki_worker(home, filed_ids)
    print(
        "note: wiki filings continue in the background — an accepted "
        "filing lands as an entry in wiki/log.md; `tapedeck wiki sync` "
        "converges anything that does not land",
        file=sys.stderr,
    )
