"""Ephemeral unit tests for ingest — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the URL forms (and
near-misses) the parser must sort out, normalization against the real schema
file, the messy info.json a real yt-dlp emits, the seam's config rules, and the
staging → install move that keeps a failed fetch out of the library.
"""

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from ingest import fetch, meta, sources  # noqa: E402
from ingest.__main__ import add, install  # noqa: E402

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "system/contracts/meta.schema.json").read_text()
)
ID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={ID}"
# A real yt-dlp info.json: the keys we want, buried in the ones we do not.
INFO = {
    "id": ID,
    "title": "  Test Video:   Building Things  ",
    "uploader": "Fixture Channel",
    "uploader_id": "@fixture",
    "upload_date": "20260115",
    "duration": 719.64,
    "webpage_url": URL,
    "description": "Line one.\n\nLine two.",
    "chapters": [
        {"title": "The Core Idea", "start_time": 95.0, "end_time": 610.0},
        {"title": "Intro", "start_time": 0, "end_time": 95.0},
    ],
    "formats": [{"format_id": "137"}],
    "thumbnails": [{"url": "https://i.ytimg.com/x.jpg"}],
    "like_count": 12,
}


@pytest.fixture
def staging():
    path = fetch.stage()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    return h


def check_schema(document):
    """The schema by hand — jsonschema is not a dependency, and the properties it
    pins (required keys, patterns, additionalProperties: false) are few."""
    assert set(SCHEMA["required"]) <= set(document)
    assert set(document) <= set(SCHEMA["properties"]), "additionalProperties: false"
    for key, value in document.items():
        rule = SCHEMA["properties"][key]
        types = {"string": str, "integer": int, "number": (int, float), "array": list}
        assert isinstance(value, types[rule["type"]]), key
        if rule.get("pattern"):
            assert re.fullmatch(rule["pattern"], value), key
        if rule.get("minLength"):
            assert len(value) >= rule["minLength"], key


# ── sources: the id, and only from a form the spec names ──────────────────────


@pytest.mark.parametrize(
    "target",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"http://youtube.com/watch?v={ID}",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://music.youtube.com/watch?v={ID}",
        f"https://www.youtube.com/watch?v={ID}&t=95s&list=PL123",
        f"https://youtu.be/{ID}",
        f"youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=95",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://youtube.com/shorts/{ID}/",
        ID,
        f"  {ID}  ",
    ],
)
def test_accepted_forms_resolve(target):
    assert sources.video_id(target) == ID


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/not-a-video",  # 11 chars in the path — not an id
        f"https://example.com/watch?v={ID}",
        f"https://notyoutube.com/watch?v={ID}",
        f"https://www.youtube.com/playlist?list={ID}",
        f"https://www.youtube.com/@channel/{ID}",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch",
        f"file:///tmp/{ID}",
        f"a video about {ID}",
        "",
        "   ",
    ],
)
def test_rejected_forms_are_usage_errors(target):
    with pytest.raises(sources.BadRequest):
        sources.video_id(target)


def test_canonical_url_is_the_deep_link_form():
    assert sources.canonical_url(ID) == URL


# ── meta: info.json narrowed to the schema ────────────────────────────────────


def test_normalize_matches_the_schema():
    document = meta.normalize(ID, URL, INFO)
    check_schema(document)
    assert document["id"] == ID
    assert document["title"] == "Test Video: Building Things"  # whitespace tidied
    assert document["channel"] == "Fixture Channel"
    assert document["upload_date"] == "2026-01-15"
    assert document["duration_s"] == 720  # rounded from 719.64
    assert document["url"] == URL
    assert document["description"] == "Line one.\n\nLine two."  # newlines survive
    assert "formats" not in document and "like_count" not in document


def test_chapters_are_ordered_and_renamed():
    assert meta.normalize(ID, URL, INFO)["chapters"] == [
        {"title": "Intro", "start_s": 0},
        {"title": "The Core Idea", "start_s": 95},
    ]
    assert isinstance(meta.normalize(ID, URL, INFO)["chapters"][0]["start_s"], int)


def test_unusable_chapters_are_dropped_not_stored():
    document = meta.normalize(ID, URL, {**INFO, "chapters": [{"title": "No time"}, "junk"]})
    assert "chapters" not in document
    negative = meta.normalize(ID, URL, {**INFO, "chapters": [{"start_time": -5.0}]})
    assert negative["chapters"] == [{"title": "", "start_s": 0}]
    check_schema(negative)


def test_a_bare_info_json_still_yields_a_valid_entry():
    document = meta.normalize(ID, URL, {}, ingested_at="2026-08-13T09:00:00+00:00")
    check_schema(document)
    assert document["title"] == ID  # a download is not stranded over a missing title
    assert document["channel"] == ""
    assert document["upload_date"] == "2026-08-13"  # dated when we ingested it
    assert document["duration_s"] == 0
    assert document["url"] == URL


@pytest.mark.parametrize(
    "info,expected",
    [
        ({"upload_date": "20260115"}, "2026-01-15"),
        ({"upload_date": "2026-01-15"}, "2026-01-15"),
        ({"upload_date": "2026-01-15T10:00:00Z"}, "2026-01-15"),
        ({"upload_date": None, "release_date": "20260202"}, "2026-02-02"),
        ({"upload_date": "not a date"}, "2026-08-13"),
    ],
)
def test_dates_normalize(info, expected):
    document = meta.normalize(ID, URL, info, ingested_at="2026-08-13T09:00:00+00:00")
    assert document["upload_date"] == expected


def test_non_object_info_is_bad_meta():
    with pytest.raises(meta.BadMeta):
        meta.normalize(ID, URL, ["not", "an", "object"])


def test_write_is_atomic_and_leaves_no_temp(tmp_path):
    entry = tmp_path / ID
    entry.mkdir()
    target = meta.write(entry, meta.normalize(ID, URL, INFO))
    assert json.loads(target.read_text())["id"] == ID
    assert [p.name for p in entry.iterdir()] == ["meta.json"]


# ── fetch: the seam, and what it left in staging ──────────────────────────────


def test_default_command_carries_lesson_0001():
    command = fetch.DEFAULT_FETCHER_COMMAND
    assert "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" in command
    assert "--no-playlist" in command and "--write-info-json" in command
    assert '"$TAPEDECK_DEST/video.%(ext)s"' in command and '"$TAPEDECK_VIDEO_URL"' in command


@pytest.mark.parametrize(
    "text", ["", "# nothing\n", "[ingest]\n", '[ingest]\nfetcher_command = ""\n', "not toml ["]
)
def test_an_unconfigured_seam_names_itself(home, text):
    (home / "config.toml").write_text(text)
    with pytest.raises(fetch.ConfigError) as caught:
        fetch.seam(home)
    assert "fetch" in str(caught.value).lower()


def test_seam_reads_the_configured_command(home):
    (home / "config.toml").write_text('[ingest]\nfetcher_command = "  yt-dlp $TAPEDECK_DEST  "\n')
    assert fetch.seam(home) == "yt-dlp $TAPEDECK_DEST"


def test_run_passes_the_seam_environment(home, staging):
    (home / "config.toml").write_text("")
    script = 'printf "%s|%s|%s" "$TAPEDECK_VIDEO_ID" "$TAPEDECK_VIDEO_URL" "$TAPEDECK_DEST" > env'
    fetch.run(script, home, ID, URL, staging)
    assert (staging / "env").read_text() == f"{ID}|{URL}|{staging}"


def test_a_failing_fetcher_raises(home, staging):
    with pytest.raises(fetch.FetchError):
        fetch.run("exit 3", home, ID, URL, staging)


def test_video_discovery_ignores_the_fetchers_leftovers(staging):
    for name in ("video.info.json", "video.mp4.part", "video.webp", "video.f299.mp4", "other.mp4"):
        (staging / name).write_text("x")
    assert not fetch.has_video(staging)
    (staging / "video.mkv").write_text("x")
    assert fetch.find_video(staging, ID).name == "video.mkv"


def test_info_json_is_found_under_either_name(staging):
    (staging / "video.info.json").write_text(json.dumps(INFO))
    assert fetch.read_info(staging, ID)["id"] == ID
    (staging / "video.info.json").unlink()
    (staging / "info.json").write_text(json.dumps(INFO))
    assert fetch.read_info(staging, ID)["id"] == ID


def test_missing_or_broken_info_json_names_it(staging):
    with pytest.raises(fetch.FetchError, match="info"):
        fetch.read_info(staging, ID)
    (staging / "info.json").write_text("{not json")
    with pytest.raises(fetch.FetchError, match="JSON"):
        fetch.read_info(staging, ID)


# ── install: nothing enters the library until the whole entry is good ─────────


def test_install_replaces_the_video_but_not_the_transcript(home, staging):
    entry = home / "library" / ID
    entry.mkdir(parents=True)
    (entry / "video.mkv").write_text("old")
    (entry / "transcript.json").write_text('{"video_id": "x"}')  # transcribe's file
    (staging / "video.mp4").write_text("new")
    install(entry, staging / "video.mp4", meta.normalize(ID, URL, INFO))
    assert sorted(p.name for p in entry.iterdir()) == ["meta.json", "transcript.json", "video.mp4"]
    assert (entry / "video.mp4").read_text() == "new"


def test_install_removes_an_entry_it_could_not_finish(home, staging):
    entry = home / "library" / ID
    with pytest.raises(OSError):  # the video vanished between staging and install
        install(entry, staging / "gone.mp4", meta.normalize(ID, URL, INFO))
    assert not entry.exists()


def test_install_keeps_an_entry_it_did_not_create(home, staging):
    """Only a directory we made is ours to remove — a failed re-fetch must not
    take an existing entry (and its transcript) down with it."""
    entry = home / "library" / ID
    entry.mkdir(parents=True)
    (entry / "transcript.json").write_text('{"video_id": "x"}')
    with pytest.raises(OSError):
        install(entry, staging / "gone.mp4", meta.normalize(ID, URL, INFO))
    assert (entry / "transcript.json").is_file()


def test_a_fetcher_that_writes_nothing_fails_before_touching_the_library(home):
    (home / "config.toml").write_text('[ingest]\nfetcher_command = "true"\n')
    with pytest.raises(fetch.FetchError):
        add(home, ID, force=False)
    assert list((home / "library").iterdir()) == []


def test_staging_never_survives_a_run(home):
    (home / "config.toml").write_text('[ingest]\nfetcher_command = "exit 1"\n')
    scratch = Path(tempfile.gettempdir())
    before = set(scratch.glob("tapedeck-ingest-*"))
    with pytest.raises(fetch.FetchError):
        add(home, ID, force=False)
    assert set(scratch.glob("tapedeck-ingest-*")) == before
