"""Ephemeral unit tests for transcribe — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the messy JSON a real
whisper CLI emits, normalization against the real schema file, the seam's config
rules (including the model label LESSON-0002 turns on), the $TAPEDECK_OUT
convention that makes the shipped default land where we read, and the atomic write
that keeps a failed re-transcription from eating the transcript already here.
"""

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from transcribe import document, transcriber  # noqa: E402
from transcribe.__main__ import BadRequest, transcribe as run_verb  # noqa: E402

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "system/contracts/transcript.schema.json").read_text()
)
ID = "dQw4w9WgXcQ"
MODEL = "fixture/whisper-0"
# A real whisper payload: leading spaces, per-segment fields nobody reads.
WHISPER = {
    "text": " Welcome to the fixture show. We are testing the transcriber.",
    "language": "en",
    "segments": [
        {
            "id": 0,
            "seek": 0,
            "start": 0.0,
            "end": 4.5,
            "text": " Welcome to the fixture show.",
            "tokens": [50364, 4027],
            "temperature": 0.0,
            "avg_logprob": -0.21,
            "compression_ratio": 1.4,
            "no_speech_prob": 0.01,
        },
        {"id": 1, "seek": 0, "start": 6.0, "end": 11.0, "text": " We are testing the transcriber."},
    ],
}


@pytest.fixture
def staging():
    path = transcriber.stage()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    return h


def entry_with_video(home, video_id=ID, ext="mp4"):
    entry = home / "library" / video_id
    entry.mkdir(parents=True, exist_ok=True)
    (entry / f"video.{ext}").write_bytes(b"\x00fixture-video")
    return entry


def set_seam(home, body, model=MODEL):
    script = home / "whisper.sh"
    script.write_text(body)
    line = f'model = "{model}"\n' if model else ""
    (home / "config.toml").write_text(
        f'[transcribe]\ntranscriber_command = "sh {script}"\n{line}'
    )


def check_schema(doc):
    """The schema by hand — jsonschema is not a dependency, and the properties it
    pins (required keys, patterns, additionalProperties: false) are few."""
    assert set(SCHEMA["required"]) <= set(doc)
    assert set(doc) <= set(SCHEMA["properties"]), "additionalProperties: false"
    assert re.fullmatch(SCHEMA["properties"]["video_id"]["pattern"], doc["video_id"])
    assert isinstance(doc["model"], str) and doc["model"]
    items = SCHEMA["properties"]["segments"]["items"]
    assert len(doc["segments"]) >= SCHEMA["properties"]["segments"]["minItems"]
    for segment in doc["segments"]:
        assert set(items["required"]) == set(segment), "additionalProperties: false"
        assert isinstance(segment["text"], str)
        for key in ("start", "end"):
            assert isinstance(segment[key], (int, float)) and not isinstance(segment[key], bool)
            assert segment[key] >= items["properties"][key]["minimum"]


# ── document: whisper's JSON narrowed to the schema ───────────────────────────


def test_normalize_produces_a_schema_shaped_transcript():
    doc = document.normalize(ID, MODEL, WHISPER)
    check_schema(doc)
    assert doc["video_id"] == ID and doc["model"] == MODEL and doc["language"] == "en"
    assert doc["segments"][0] == {"start": 0.0, "end": 4.5, "text": "Welcome to the fixture show."}
    assert doc["transcribed_at"].startswith("20")


def test_segments_are_ordered_and_stripped():
    doc = document.normalize(
        ID,
        MODEL,
        {
            "segments": [
                {"start": 6.0, "end": 11.0, "text": "  second\n  line  "},
                {"start": 0.0, "end": 4.5, "text": " first "},
            ]
        },
    )
    assert [s["text"] for s in doc["segments"]] == ["first", "second line"]


@pytest.mark.parametrize(
    "segment",
    [
        {"start": None, "end": 4.5, "text": "no start"},
        {"start": 0.0, "text": "no end"},
        {"start": "0.0", "end": "4.5", "text": "times as strings"},
        {"start": True, "end": 4.5, "text": "a bool is not a timestamp"},
        {"start": 0.0, "end": 4.5, "text": "   "},
        {"start": 0.0, "end": 4.5},
        "not even an object",
    ],
)
def test_unusable_segments_are_dropped(segment):
    keep = {"start": 20.0, "end": 24.0, "text": "the real one"}
    assert document.segments([segment, keep]) == [keep]


def test_a_backwards_segment_keeps_its_start():
    assert document.segments([{"start": 9.0, "end": 3.0, "text": "hi"}]) == [
        {"start": 9.0, "end": 9.0, "text": "hi"}
    ]


def test_negative_times_are_clamped_and_precision_is_milliseconds():
    raw = {"segments": [{"start": -0.5, "end": 4.500001, "text": "x"}]}
    assert document.normalize(ID, MODEL, raw)["segments"] == [{"start": 0.0, "end": 4.5, "text": "x"}]


@pytest.mark.parametrize("payload", [{}, {"segments": []}, {"segments": 7}, {"segments": [{}]}])
def test_a_transcript_with_no_segments_is_an_error(payload):
    with pytest.raises(document.BadTranscript):
        document.normalize(ID, MODEL, payload)


@pytest.mark.parametrize("language", [None, "", "   ", 7])
def test_language_is_omitted_when_the_transcriber_names_none(language):
    doc = document.normalize(ID, MODEL, {"language": language, "segments": WHISPER["segments"]})
    assert "language" not in doc
    check_schema(doc)


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = document.write(tmp_path, document.normalize(ID, MODEL, WHISPER))
    assert json.loads(target.read_text())["video_id"] == ID
    assert [p.name for p in tmp_path.iterdir()] == ["transcript.json"]


# ── transcriber: the seam, its config, and its scratch space ──────────────────


def test_shipped_default_is_lesson_0002_verbatim():
    assert transcriber.DEFAULT_TRANSCRIBER_COMMAND == (
        "mlx_whisper --model mlx-community/whisper-large-v3-turbo "
        "--condition-on-previous-text False --output-format json "
        '--output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
    )
    assert transcriber.DEFAULT_MODEL == "mlx-whisper/large-v3-turbo"


def test_out_path_meets_the_whisper_output_dir_convention(staging):
    # The default passes --output-dir "$(dirname $TAPEDECK_OUT)" and whisper names
    # the file <input-stem>.json inside it: the two must be the same path.
    out = transcriber.out_path(staging, Path("/lib/dQw4w9WgXcQ/video.mkv"))
    assert out == staging / "video.json"
    assert out.parent == staging


def test_seam_reads_the_command_and_the_label(home):
    set_seam(home, "#!/bin/sh\n", model="fixture/whisper-1")
    command, model = transcriber.seam(home)
    assert command.startswith("sh ") and model == "fixture/whisper-1"


@pytest.mark.parametrize(
    "config",
    [
        "",
        "# nothing here\n",
        "[transcribe]\n",
        '[transcribe]\ntranscriber_command = ""\n',
        '[transcribe]\ntranscriber_command = "   "\n',
        "[transcribe]\ntranscriber_command = 42\n",
        "[ingest]\nfetcher_command = 'yt-dlp'\n",
        "this is not toml at all\n",
    ],
)
def test_an_unconfigured_seam_is_a_config_error(home, config):
    (home / "config.toml").write_text(config)
    with pytest.raises(transcriber.ConfigError) as caught:
        transcriber.seam(home)
    assert "transcriber" in str(caught.value)


def test_a_missing_config_file_is_a_config_error(home):
    with pytest.raises(transcriber.ConfigError):
        transcriber.seam(home)


def test_the_shipped_command_supplies_its_own_label(home):
    (home / "config.toml").write_text(
        "[transcribe]\ntranscriber_command = "
        f"'{transcriber.DEFAULT_TRANSCRIBER_COMMAND}'\n"
    )
    assert transcriber.seam(home)[1] == transcriber.DEFAULT_MODEL


def test_an_unlabelled_custom_command_is_a_config_error(home):
    # LESSON-0002: supersession is judged on the label, so we never stamp the
    # shipped model onto transcripts produced by something else.
    set_seam(home, "#!/bin/sh\n", model=None)
    with pytest.raises(transcriber.ConfigError) as caught:
        transcriber.seam(home)
    assert "model" in str(caught.value)


@pytest.mark.parametrize("ext", ["mp4", "mkv", "webm"])
def test_media_is_found_whatever_the_container(home, ext):
    entry = entry_with_video(home, ext=ext)
    (entry / "meta.json").write_text("{}")
    (entry / "transcript.json").write_text("{}")
    (entry / "video.info.json").write_text("{}")
    assert transcriber.media(entry, ID).name == f"video.{ext}"


@pytest.mark.parametrize("leftovers", [[], ["meta.json"], ["video.part"], ["video.jpg"]])
def test_an_entry_without_a_video_is_a_clear_failure(home, leftovers):
    entry = home / "library" / ID
    entry.mkdir(parents=True)
    for name in leftovers:
        (entry / name).write_text("x")
    with pytest.raises(transcriber.TranscribeError) as caught:
        transcriber.media(entry, ID)
    assert "video" in str(caught.value)


def test_run_hands_the_seam_its_environment(home, staging):
    entry = entry_with_video(home)
    out = transcriber.out_path(staging, entry / "video.mp4")
    transcriber.run(
        'printf \'{"media":"%s","id":"%s","out":"%s"}\' '
        '"$TAPEDECK_MEDIA" "$TAPEDECK_VIDEO_ID" "$TAPEDECK_OUT" > "$TAPEDECK_OUT"; '
        "touch sidecar.txt",
        home,
        ID,
        entry / "video.mp4",
        out,
    )
    seen = json.loads(out.read_text())
    assert seen == {"media": str(entry / "video.mp4"), "id": ID, "out": str(out)}
    # cwd is the staging dir, so a sidecar written relative lands outside the library
    assert (staging / "sidecar.txt").is_file()
    assert not (entry / "sidecar.txt").exists()


def test_a_nonzero_transcriber_raises(home, staging):
    with pytest.raises(transcriber.TranscribeError) as caught:
        transcriber.run("exit 3", home, ID, Path("video.mp4"), staging / "video.json")
    assert "3" in str(caught.value)


@pytest.mark.parametrize("body", [None, "not json", "[1, 2, 3]", '"a string"'])
def test_output_that_is_not_a_json_object_raises(staging, body):
    out = staging / "video.json"
    if body is not None:
        out.write_text(body)
    with pytest.raises(transcriber.TranscribeError):
        transcriber.read_output(out, ID)


# ── the verb: skip, force, and what a failure leaves behind ───────────────────


WRITES_TRANSCRIPT = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/count"
printf '{"language":"en","segments":[{"start":0,"end":2,"text":" hello"}]}' > "$TAPEDECK_OUT"
"""


def test_verb_writes_the_transcript_and_is_idempotent(home, capsys):
    entry = entry_with_video(home)
    set_seam(home, WRITES_TRANSCRIPT)
    assert run_verb(home, ID, force=False) == 0
    assert run_verb(home, ID, force=False) == 0
    assert (home / "count").read_text().count("run") == 1
    assert run_verb(home, ID, force=True) == 0
    assert (home / "count").read_text().count("run") == 2
    check_schema(json.loads((entry / "transcript.json").read_text()))
    assert capsys.readouterr().out.strip().endswith("transcript.json")


def test_a_failed_re_transcription_keeps_the_transcript_already_here(home):
    entry = entry_with_video(home)
    set_seam(home, WRITES_TRANSCRIPT)
    assert run_verb(home, ID, force=False) == 0
    before = (entry / "transcript.json").read_text()
    set_seam(home, "#!/bin/sh\nexit 1\n")
    with pytest.raises(transcriber.TranscribeError):
        run_verb(home, ID, force=True)
    assert (entry / "transcript.json").read_text() == before, "the old transcript survived"


def test_a_failed_first_transcription_leaves_the_entry_untouched(home):
    entry = entry_with_video(home)
    set_seam(home, '#!/bin/sh\nprintf "garbage" > "$TAPEDECK_OUT"\n')
    with pytest.raises(transcriber.TranscribeError):
        run_verb(home, ID, force=False)
    assert sorted(p.name for p in entry.iterdir()) == ["video.mp4"]


def test_a_silent_transcriber_writes_nothing(home):
    entry = entry_with_video(home)
    set_seam(home, '#!/bin/sh\nprintf \'{"segments":[]}\' > "$TAPEDECK_OUT"\n')
    with pytest.raises(document.BadTranscript):
        run_verb(home, ID, force=False)
    assert not (entry / "transcript.json").exists()


def test_the_verb_leaves_no_scratch_directories_behind(home, tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    # tempfile caches gettempdir(), so $TMPDIR alone would not redirect mkdtemp here
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    entry_with_video(home)
    set_seam(home, WRITES_TRANSCRIPT)
    assert run_verb(home, ID, force=False) == 0
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("target", ["", "  ", "tooshort", "wayyyyytoolongforanid", "bad/id/here"])
def test_an_id_that_names_no_entry_is_a_usage_error(home, target):
    with pytest.raises(BadRequest):
        run_verb(home, target, force=False)
