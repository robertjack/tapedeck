"""Shared harness for tapedeck durable evaluations.

Component boundary: each generated component is runnable as `python -m <name>`
(overridable via $TAPEDECK_<NAME>_CMD), with the library resolved from
$TAPEDECK_HOME. Evals drive that subprocess boundary only — never imports —
so implementations stay replaceable. Fixture libraries are built in tmp dirs
per system/contracts/library-layout.md.
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TIMEOUT = 120


def run_component(module, args, home):
    cmd = os.environ.get(f"TAPEDECK_{module.upper()}_CMD", f"{sys.executable} -m {module}")
    return subprocess.run(
        [*shlex.split(cmd), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={**os.environ, "TAPEDECK_HOME": str(home)},
    )


CHAPTERED_META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video: Building Things",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "chapters": [
        {"title": "Intro", "start_s": 0},
        {"title": "The Core Idea", "start_s": 95},
        {"title": "Wrap Up", "start_s": 610},
    ],
}
CHAPTERED_SEGMENTS = [
    {"start": 0.0, "end": 4.5, "text": "Welcome to the fixture show."},
    {"start": 6.0, "end": 11.0, "text": "We are testing the archive renderer."},
    {"start": 96.0, "end": 103.5, "text": "The core idea is regeneration over maintenance."},
    {"start": 612.5, "end": 619.0, "text": "Thanks for watching, goodbye."},
]

PLAIN_META = {
    "id": "plainvide00",
    "title": "Sourdough Basics",
    "channel": "Bread Channel",
    "upload_date": "2026-02-02",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=plainvide00",
}
PLAIN_SEGMENTS = [
    {"start": 2.0, "end": 6.0, "text": "Block one content about sourdough starters."},
    {"start": 310.0, "end": 316.0, "text": "Block two content about proofing times."},
    {"start": 640.0, "end": 646.0, "text": "Block three content about scoring loaves."},
]


def add_video(home, meta, segments=None):
    d = home / "library" / meta["id"]
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"\x00fixture-video")
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    if segments is not None:
        (d / "transcript.json").write_text(
            json.dumps(
                {"video_id": meta["id"], "model": "fixture/whisper-0", "segments": segments},
                indent=2,
            )
        )


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    (h / "config.toml").write_text("# fixture config\n")
    return h
