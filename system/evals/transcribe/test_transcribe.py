"""Durable evals: transcribe (SPEC-transcribe-001, SPEC-core-004).

Boundary: `python -m transcribe run <id> [--force]`, library via $TAPEDECK_HOME,
transcriber via config.toml [transcribe] (see conftest.set_transcriber for the
pinned interface).
"""

import json

from conftest import CHAPTERED_META, add_video, run_component, set_transcriber

WHISPER_OK = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/whisper-count"
cat > "$TAPEDECK_OUT" <<'JSON'
{"language": "en", "segments": [
  {"start": 0.0, "end": 4.5, "text": " Welcome to the fixture show."},
  {"start": 6.0, "end": 11.0, "text": " We are testing the transcriber."}
]}
JSON
"""
WHISPER_FAILS = """#!/bin/sh
exit 1
"""
WHISPER_GARBAGE = """#!/bin/sh
printf 'not json at all' > "$TAPEDECK_OUT"
"""


def run(home, *args):
    return run_component("transcribe", ["run", *args], home)


def ready_video(home):
    add_video(home, CHAPTERED_META, segments=None)  # video + meta, no transcript


def test_transcript_is_normalized_and_schema_shaped(home):
    ready_video(home)
    set_transcriber(home, WHISPER_OK)
    r = run(home, "dQw4w9WgXcQ")
    assert r.returncode == 0, r.stderr
    t = json.loads((home / "library" / "dQw4w9WgXcQ" / "transcript.json").read_text())
    assert t["video_id"] == "dQw4w9WgXcQ"
    assert t["model"] == "fixture/whisper-0"
    assert t["segments"][0] == {"start": 0.0, "end": 4.5, "text": "Welcome to the fixture show."}
    assert t["segments"][1]["text"] == "We are testing the transcriber."


def test_existing_transcript_skips_unless_forced(home):
    ready_video(home)
    set_transcriber(home, WHISPER_OK)
    assert run(home, "dQw4w9WgXcQ").returncode == 0
    assert run(home, "dQw4w9WgXcQ").returncode == 0
    assert (home / "whisper-count").read_text().count("run") == 1
    assert run(home, "dQw4w9WgXcQ", "--force").returncode == 0
    assert (home / "whisper-count").read_text().count("run") == 2


def test_failed_transcriber_leaves_no_partial_transcript(home):
    ready_video(home)
    set_transcriber(home, WHISPER_FAILS)
    r = run(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert not (home / "library" / "dQw4w9WgXcQ" / "transcript.json").exists()


def test_garbage_transcriber_output_fails_cleanly(home):
    ready_video(home)
    set_transcriber(home, WHISPER_GARBAGE)
    r = run(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert not (home / "library" / "dQw4w9WgXcQ" / "transcript.json").exists()


def test_missing_video_file_is_a_clear_error(home):
    d = home / "library" / "dQw4w9WgXcQ"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(CHAPTERED_META))
    set_transcriber(home, WHISPER_OK)
    r = run(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert "video" in r.stderr.lower()


def test_missing_transcriber_config_is_an_error(home):
    ready_video(home)
    (home / "config.toml").write_text("# no transcribe section\n")
    r = run(home, "dQw4w9WgXcQ")
    assert r.returncode == 2
    assert "transcriber" in r.stderr.lower()
