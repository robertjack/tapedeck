"""Durable evals: retranscribe sweep + adapt-parakeet surface (SPEC-cli-004).

Boundary: the `tapedeck` executable; transcriber seam faked through
config.toml. Supersession is judged on the transcript's `model` label vs the
configured [transcribe].model (SPEC-transcribe-001).
"""

import json
import os
import shlex
import subprocess

from conftest import (
    CHAPTERED_META,
    CHAPTERED_SEGMENTS,
    PLAIN_META,
    PLAIN_SEGMENTS,
    REPO,
    TIMEOUT,
    add_video,
    run_cli,
)

WHISPER_V2 = """#!/bin/sh
echo "$TAPEDECK_VIDEO_ID" >> "$TAPEDECK_HOME/whisper-log"
cat > "$TAPEDECK_OUT" <<'JSON'
{"segments": [{"start": 1.0, "end": 5.0, "text": " Upgraded fixture transcript."}]}
JSON
"""


def set_upgraded_library(home):
    """Two videos: one already on the configured model, one on the old label."""
    script = home / "whisper2.sh"
    script.write_text(WHISPER_V2)
    (home / "config.toml").write_text(
        f'[transcribe]\ntranscriber_command = "sh {script}"\nmodel = "fixture/whisper-2"\n'
    )
    add_video(home, CHAPTERED_META, CHAPTERED_SEGMENTS)  # labelled fixture/whisper-0
    add_video(home, PLAIN_META, PLAIN_SEGMENTS)          # labelled fixture/whisper-0
    current = home / "library" / PLAIN_META["id"] / "transcript.json"
    doc = json.loads(current.read_text())
    doc["model"] = "fixture/whisper-2"                   # this one is already current
    current.write_text(json.dumps(doc, indent=2))


def test_retranscribe_sweeps_only_superseded_labels(home):
    set_upgraded_library(home)
    r = run_cli(["retranscribe"], home)
    assert r.returncode == 0, r.stderr
    assert (home / "whisper-log").read_text().split() == [CHAPTERED_META["id"]]
    redone = json.loads(
        (home / "library" / CHAPTERED_META["id"] / "transcript.json").read_text()
    )
    assert redone["model"] == "fixture/whisper-2"
    assert "Upgraded fixture transcript." in (
        home / "archive" / f"{CHAPTERED_META['id']}.md"
    ).read_text()
    results = json.loads(run_cli(["search", "Upgraded", "--json"], home).stdout)
    assert results and results[0]["video_id"] == CHAPTERED_META["id"]
    untouched = json.loads(
        (home / "library" / PLAIN_META["id"] / "transcript.json").read_text()
    )
    assert untouched["segments"] == PLAIN_SEGMENTS


def test_retranscribe_is_idempotent(home):
    set_upgraded_library(home)
    assert run_cli(["retranscribe"], home).returncode == 0
    assert run_cli(["retranscribe"], home).returncode == 0
    assert (home / "whisper-log").read_text().split() == [CHAPTERED_META["id"]]


def test_dry_run_lists_but_touches_nothing(home):
    set_upgraded_library(home)
    r = run_cli(["retranscribe", "--dry-run"], home)
    assert r.returncode == 0, r.stderr
    assert CHAPTERED_META["id"] in r.stdout.split()
    assert PLAIN_META["id"] not in r.stdout.split()
    assert not (home / "whisper-log").exists()


def test_adapt_parakeet_is_on_the_installed_surface(home):
    payload = json.dumps(
        {"text": "Hi.", "sentences": [
            {"text": "Hi.", "start": 0.5, "end": 1.0, "duration": 0.5,
             "confidence": 0.9, "tokens": []},
        ]}
    )
    cmd = os.environ.get("TAPEDECK_BIN", "tapedeck")
    r = subprocess.run(
        [*shlex.split(cmd), "adapt-parakeet"],
        cwd=REPO,
        input=payload,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={**os.environ, "TAPEDECK_HOME": str(home)},
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["segments"] == [{"start": 0.5, "end": 1.0, "text": "Hi."}]
