"""Ephemeral unit tests for transcribe — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: normalization against the
real schema file, the messy segment shapes a real whisper emits, the seam's config
rules, and the atomic write that protects an existing transcript.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from transcribe import document, transcriber  # noqa: E402

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "system/contracts/transcript.schema.json").read_text()
)
ID = "dQw4w9WgXcQ"
MODEL = "fixture/whisper-0"
WHISPER = {
    "text": "the whole thing as one string",
    "language": "en",
    "segments": [
        {"id": 0, "seek": 0, "start": 0.0, "end": 4.5, "text": " Welcome to the show. ",
         "tokens": [1, 2], "temperature": 0.0, "avg_logprob": -0.2, "no_speech_prob": 0.01},
        {"id": 1, "seek": 400, "start": 6.0, "end": 11.0, "text": "We are\ntesting it."},
    ],
}


@pytest.fixture
def staging():
    path = transcriber.stage()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def check_schema(doc):
    """Enough of transcript.schema.json to catch a drifting normalizer, no dependency."""
    kinds = {"string": str, "number": (int, float), "array": list, "object": dict}

    def check(value, spec, where):
        assert isinstance(value, kinds[spec["type"]]), f"{where} is not {spec['type']}"
        if "pattern" in spec:
            assert re.fullmatch(spec["pattern"], value), f"{where}={value!r} fails its pattern"
        if "minimum" in spec:
            assert value >= spec["minimum"], f"{where}={value} below minimum"
        if spec["type"] == "array":
            assert len(value) >= spec.get("minItems", 0), f"{where} is too short"
            for i, item in enumerate(value):
                check(item, spec["items"], f"{where}[{i}]")
        if spec["type"] == "object":
            for key in spec["required"]:
                assert key in value, f"{where} is missing required {key}"
            for key, sub in value.items():
                assert key in spec["properties"], f"additionalProperties: false forbids {key}"
                check(sub, spec["properties"][key], f"{where}.{key}")

    check(doc, SCHEMA, "transcript")


# --- normalization -----------------------------------------------------------


def test_normalize_matches_the_schema_and_drops_unknown_fields():
    doc = document.normalize(ID, MODEL, WHISPER)
    check_schema(doc)
    assert doc["video_id"] == ID and doc["model"] == MODEL and doc["language"] == "en"
    assert doc["segments"] == [
        {"start": 0.0, "end": 4.5, "text": "Welcome to the show."},
        {"start": 6.0, "end": 11.0, "text": "We are testing it."},
    ]
    assert list(doc)[:2] == SCHEMA["required"][:2]
    assert "text" not in doc  # the whole-transcript blob is not part of the contract


def test_segments_are_ordered_and_timestamps_made_sane():
    doc = document.normalize(
        ID,
        MODEL,
        {
            "segments": [
                {"start": 30, "end": 20, "text": "second, and ends before it starts"},
                {"start": -3.0, "end": 2.0, "text": "first, from a negative start"},
            ]
        },
    )
    check_schema(doc)
    assert [s["start"] for s in doc["segments"]] == [0.0, 30.0]
    assert doc["segments"][1]["end"] == 30.0  # never before its own start


@pytest.mark.parametrize(
    "segment",
    [
        {"end": 4.0, "text": "no start"},
        {"start": 1.0, "text": "no end"},
        {"start": None, "end": 4.0, "text": "untimed"},
        {"start": True, "end": 4.0, "text": "a bool is not a timestamp"},
        {"start": "1.0", "end": "4.0", "text": "stringly timed"},
        {"start": 1.0, "end": 4.0, "text": "   "},
        {"start": 1.0, "end": 4.0},
        "not a segment at all",
    ],
)
def test_unusable_segments_are_dropped_not_guessed(segment):
    keeper = {"start": 90.0, "end": 92.0, "text": "keep me"}
    doc = document.normalize(ID, MODEL, {"segments": [segment, keeper]})
    assert doc["segments"] == [keeper]


@pytest.mark.parametrize(
    "output",
    [
        {"segments": []},
        {"segments": "not a list"},
        {"text": "no segments key at all"},
        {"segments": [{"start": 0, "end": 1, "text": ""}]},
        [{"start": 0, "end": 1, "text": "a bare list"}],
        "not an object",
    ],
)
def test_output_without_timestamped_segments_is_a_bad_transcript(output):
    with pytest.raises(document.BadTranscript):
        document.normalize(ID, MODEL, output)


def test_language_is_optional_and_never_blank():
    for language in (None, "", "   ", 7):
        doc = document.normalize(ID, MODEL, {"language": language, "segments": WHISPER["segments"]})
        check_schema(doc)
        assert "language" not in doc


def test_transcribed_at_is_recorded():
    doc = document.normalize(ID, MODEL, WHISPER, transcribed_at="2026-08-12T00:00:00+00:00")
    assert doc["transcribed_at"] == "2026-08-12T00:00:00+00:00"
    assert document.normalize(ID, MODEL, WHISPER)["transcribed_at"].endswith("+00:00")


# --- the write ---------------------------------------------------------------


def test_write_is_atomic_and_leaves_no_scratch_behind(tmp_path):
    doc = document.normalize(ID, MODEL, WHISPER)
    target = document.write(tmp_path, doc)
    assert target.name == "transcript.json"
    assert json.loads(target.read_text()) == doc
    assert [p.name for p in tmp_path.iterdir()] == ["transcript.json"]


def test_write_replaces_a_previous_transcript_in_place(tmp_path):
    (tmp_path / "transcript.json").write_text('{"model": "old"}')
    document.write(tmp_path, document.normalize(ID, "new/model", WHISPER))
    assert json.loads((tmp_path / "transcript.json").read_text())["model"] == "new/model"


# --- the seam ----------------------------------------------------------------


def test_seam_requires_the_section(tmp_path):
    (tmp_path / "config.toml").write_text("[ingest]\nfetcher_command = 'sh f.sh'\n")
    with pytest.raises(transcriber.ConfigError, match="transcriber"):
        transcriber.seam(tmp_path)
    (tmp_path / "config.toml").write_text("[transcribe]\ntranscriber_command = ''\n")
    with pytest.raises(transcriber.ConfigError, match="transcriber"):
        transcriber.seam(tmp_path)
    (tmp_path / "config.toml").write_text("[transcribe\nbroken = ")
    with pytest.raises(transcriber.ConfigError):
        transcriber.seam(tmp_path)
    with pytest.raises(transcriber.ConfigError, match="transcriber"):
        transcriber.seam(tmp_path / "nowhere")


def test_seam_labels_an_unlabelled_transcriber_honestly(tmp_path):
    (tmp_path / "config.toml").write_text("[transcribe]\ntranscriber_command = ' sh w.sh '\n")
    assert transcriber.seam(tmp_path) == ("sh w.sh", transcriber.UNLABELLED_MODEL)
    (tmp_path / "config.toml").write_text(
        "[transcribe]\ntranscriber_command = 'sh w.sh'\nmodel = ' m/1 '\n"
    )
    assert transcriber.seam(tmp_path) == ("sh w.sh", "m/1")


def test_find_media_ignores_the_other_components_files(tmp_path):
    entry = tmp_path / "library" / ID
    entry.mkdir(parents=True)
    for name in ("meta.json", "transcript.json", "video.mp4.part"):
        (entry / name).write_text(name)
    with pytest.raises(transcriber.TranscribeError, match="video"):
        transcriber.find_media(entry, ID)
    with pytest.raises(transcriber.TranscribeError, match="video"):
        transcriber.find_media(tmp_path / "library" / "nosuchvideo", ID)
    (entry / "video.mkv").write_bytes(b"real")
    assert transcriber.find_media(entry, ID).name == "video.mkv"


def test_run_hands_the_seam_its_environment_and_reads_the_output(tmp_path, staging):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")
    script = (
        'printf \'{"segments": [{"start": 0, "end": 1, "text": "%s"}]}\' '
        '"$TAPEDECK_VIDEO_ID $(basename $TAPEDECK_MEDIA) $(basename $TAPEDECK_OUT)" '
        '> "$TAPEDECK_OUT"'
    )
    output = transcriber.run(script, tmp_path, ID, media, staging)
    assert output["segments"][0]["text"] == f"{ID} video.mp4 video.json"
    assert (staging / "video.json").is_file()  # named for the media, per the default command


@pytest.mark.parametrize(
    "script",
    ["exit 3", "true", 'printf "not json" > "$TAPEDECK_OUT"', "no-such-command-anywhere"],
)
def test_run_reports_every_way_the_seam_can_fail(tmp_path, staging, script):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")
    with pytest.raises(transcriber.TranscribeError):
        transcriber.run(script, tmp_path, ID, media, staging)


def test_stage_is_a_scratch_dir_outside_the_library(tmp_path, staging):
    """The transcriber's leftovers never land in an entry (SPEC-core-001)."""
    assert staging.is_dir()
    assert not str(staging).startswith(str(tmp_path))
    assert not any(staging.iterdir())
