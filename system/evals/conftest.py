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


def hms(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def write_archive_page(home, meta, sections):
    """Write archive/<id>.md directly, in the pinned SPEC-archive-001 shape
    (frontmatter, then '## [h:mm:ss](deep-link) Title' sections) — so suites for
    downstream components stay independent of the archive implementation."""
    (home / "archive").mkdir(exist_ok=True)
    vid = meta["id"]
    lines = [
        "---",
        f"id: {vid}",
        f'title: "{meta["title"]}"',
        f"channel: {meta['channel']}",
        f"upload_date: {meta['upload_date']}",
        f"duration_s: {meta['duration_s']}",
        f"url: {meta['url']}",
        "---",
        "",
        f"# {meta['title']}",
        "",
    ]
    for start_s, title, text in sections:
        url = f"https://www.youtube.com/watch?v={vid}&t={int(start_s)}s"
        lines += [f"## [{hms(start_s)}]({url}) {title}", "", text, ""]
    (home / "archive" / f"{vid}.md").write_text("\n".join(lines))


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


def set_fetcher(home, script_body):
    """Configure the SPEC-core-004 fetcher seam with a fake. Interface pinned here:
    the fetcher runs as a shell command with env TAPEDECK_VIDEO_ID, TAPEDECK_VIDEO_URL,
    and TAPEDECK_DEST (an existing directory); it must create video.<ext> plus a
    yt-dlp-shaped info.json in $TAPEDECK_DEST. ingest normalizes info.json into the
    meta.schema.json form."""
    script = home / "fetch.sh"
    script.write_text(script_body)
    (home / "config.toml").write_text(f'[ingest]\nfetcher_command = "sh {script}"\n')


def set_transcriber(home, script_body, model="fixture/whisper-0"):
    """Configure the SPEC-core-004 transcriber seam with a fake. Interface pinned
    here: the transcriber runs as a shell command with env TAPEDECK_MEDIA (path to
    the video file), TAPEDECK_VIDEO_ID, and TAPEDECK_OUT (a file path chosen by the
    component); it must write whisper-style JSON ({"segments":[{start,end,text}...]})
    to $TAPEDECK_OUT. The transcribe component normalizes that into transcript.json
    (video_id, model label from config, stripped segment text)."""
    script = home / "whisper.sh"
    script.write_text(script_body)
    (home / "config.toml").write_text(
        f'[transcribe]\ntranscriber_command = "sh {script}"\nmodel = "{model}"\n'
    )


def set_answerer(home, script_body):
    """Configure the SPEC-core-004 answerer seam with a fake. Interface pinned
    here: the answerer runs as a shell command with the assembled prompt on stdin
    and prints the answer prose (with [n] citation markers) to stdout. The Sources
    section is assembled by tapedeck from retrieval results, never by the answerer
    (contracts/ask-citations.md)."""
    script = home / "answer.sh"
    script.write_text(script_body)
    (home / "config.toml").write_text(f'[ask]\nanswerer_command = "sh {script}"\n')


def run_cli(args, home):
    """Drive the user-facing `tapedeck` executable (override via $TAPEDECK_BIN)."""
    cmd = os.environ.get("TAPEDECK_BIN", "tapedeck")
    return subprocess.run(
        [*shlex.split(cmd), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={**os.environ, "TAPEDECK_HOME": str(home)},
    )


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    (h / "config.toml").write_text("# fixture config\n")
    return h
