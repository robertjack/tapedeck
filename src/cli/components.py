"""Shared plumbing: invoking the other components as subprocesses, and
reading the read-only vocabulary they publish (LESSON-0003) rather than
re-deriving it — the video id grammar and what counts as downloaded media
are ingest's, consumed here, never rewritten.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ingest import fetch as ingest_fetch
from ingest import sources as ingest_sources

VIDEO_ID = ingest_sources.VIDEO_ID


def env_for(home: Path, **extra: str) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home), **extra}


def run_quiet(module: str, args: list[str], home: Path) -> int:
    """`python -m <module> <args>` with our stdout kept clean for cli's own
    summaries; the child's stderr streams straight through, which is where
    every component's own progress and diagnostics already go."""
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        env=env_for(home),
        stdout=subprocess.DEVNULL,
    )
    return result.returncode


def run_passthrough(module: str, args: list[str], home: Path) -> int:
    """`python -m <module> <args>` with stdio fully inherited — a direct
    delegation (search, ask, reindex, the wiki group) where the component's
    own stdout and stderr are the user's, unedited."""
    result = subprocess.run([sys.executable, "-m", module, *args], env=env_for(home))
    return result.returncode


def run_capture_stdout(module: str, args: list[str], home: Path) -> tuple[int, str]:
    """Like `run_passthrough`, but stdout is ours to read — for a listing
    whose lines become the sweep's own work list, while progress on stderr
    still streams live."""
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        env=env_for(home),
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.returncode, result.stdout or ""


def spawn_detached(module: str, args: list[str], home: Path) -> None:
    """Launch `python -m <module> <args>` as an independent process and
    return without waiting on it (SPEC-cli-011). No pipe is inherited — a
    child holding any of the caller's stdio keeps every reader of that
    stream waiting until the child ends too, which is the caller not
    returning, with extra steps — and `start_new_session` puts it in its own
    session so it outlives the caller's process group rather than dying
    with it."""
    subprocess.Popen(
        [sys.executable, "-m", module, *args],
        env=env_for(home),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_video_id(text: str) -> bool:
    return bool(VIDEO_ID.fullmatch(text or ""))


def has_media(entry: Path) -> bool:
    return ingest_fetch.has_video(entry)


def video_files(entry: Path) -> list[Path]:
    return ingest_fetch.videos(entry)


def staging_video(name: str) -> str | None:
    """The video id a `.fetching-*` directory of ours is downloading, or
    None — ingest's own answer to SPEC-ingest-003, never re-derived here."""
    return ingest_fetch.staging(name)
