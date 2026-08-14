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


# --- SPEC-cli-004: the sweep only selects what it could actually re-derive ----
#
# A library accumulates entries the sweep can never satisfy: `rm --media-only`
# keeps the knowledge and drops the video, so that transcript's label can never be
# brought up to date without downloading the video again, and a user's own
# directory under library/ is not a video at all. Selecting them means the sweep
# fails forever — it can never reach the no-op the clause promises.

NOT_A_VIDEO = "reading-notes"


def set_unre_derivable_library(home):
    """One video that can be redone, one whose media was reclaimed, and one
    directory under library/ that is not a video id at all."""
    set_upgraded_library(home)
    stripped = home / "library" / PLAIN_META["id"]
    doc = json.loads((stripped / "transcript.json").read_text())
    doc["model"] = "fixture/whisper-0"          # stale label…
    (stripped / "transcript.json").write_text(json.dumps(doc, indent=2))
    for path in stripped.glob("video.*"):       # …and no video to redo it from
        path.unlink()
    (home / "library" / NOT_A_VIDEO).mkdir()
    (home / "library" / NOT_A_VIDEO / "scratch.md").write_text("mine, not tapedeck's\n")


def test_the_sweep_skips_what_it_could_never_re_derive(home):
    set_unre_derivable_library(home)
    r = run_cli(["retranscribe"], home)
    assert r.returncode == 0, (
        "entries the sweep cannot re-derive must not fail it: " + r.stderr
    )
    assert (home / "whisper-log").read_text().split() == [CHAPTERED_META["id"]]
    assert PLAIN_META["id"] in r.stderr, "a skipped media-less entry must be reported"
    kept = json.loads((home / "library" / PLAIN_META["id"] / "transcript.json").read_text())
    assert kept["segments"] == PLAIN_SEGMENTS, "the kept knowledge must be untouched"
    assert (home / "library" / NOT_A_VIDEO / "scratch.md").is_file()


def test_the_sweep_converges_to_a_no_op(home):
    set_unre_derivable_library(home)
    assert run_cli(["retranscribe"], home).returncode == 0
    again = run_cli(["retranscribe"], home)
    assert again.returncode == 0, (
        "a library with media-less entries must still reach a no-op: " + again.stderr
    )
    assert (home / "whisper-log").read_text().split() == [CHAPTERED_META["id"]]


def test_dry_run_lists_only_what_the_sweep_would_redo(home):
    set_unre_derivable_library(home)
    r = run_cli(["retranscribe", "--dry-run"], home)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [CHAPTERED_META["id"]], (
        "--dry-run must promise exactly what the sweep would do"
    )
    assert PLAIN_META["id"] in r.stderr
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
