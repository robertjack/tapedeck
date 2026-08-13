"""Ephemeral unit tests for ingest — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the URL forms (and
near-misses) the parser must sort out on both sides of the video/collection
line, normalization against the real schema file, the messy info.json a real
yt-dlp emits, the seams' config rules, the lister's output filtering, and the
staging → install move that keeps a failed fetch out of the library.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from ingest import fetch, meta, sources  # noqa: E402
from ingest.__main__ import add, expand, install  # noqa: E402

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


real_stage = fetch.stage  # kept for tests that monkeypatch the staging ground


@pytest.fixture
def staging():
    path = real_stage()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    return h


def config(home, body):
    (home / "config.toml").write_text(body)


def script(home, name, body):
    path = home / name
    path.write_text(body)
    return f"sh {path}"


# ---------------------------------------------------------------- sources: videos


@pytest.mark.parametrize(
    "target",
    [
        ID,
        f"  {ID}  ",
        f"https://www.youtube.com/watch?v={ID}",
        f"http://youtube.com/watch?v={ID}",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://www.youtube.com/watch?v={ID}&t=42s",
        # a watch URL inside a playlist is still one video (--no-playlist)
        f"https://www.youtube.com/watch?v={ID}&list=PLabc&index=3",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=90",
        f"youtu.be/{ID}",
        f"https://www.youtube.com/shorts/{ID}",
        f"www.youtube.com/shorts/{ID}",
    ],
)
def test_video_forms_resolve_to_the_id(target):
    assert sources.resolve(target) == (sources.VIDEO, ID)
    assert sources.video_id(target) == ID


@pytest.mark.parametrize(
    "target",
    [
        "",
        "   ",
        "not a url",
        "https://example.com/not-a-video",
        # an 11-character path segment on another host is not an id
        f"https://example.com/{ID}",
        f"https://vimeo.com/watch?v={ID}",
        # a real id buried in a string is not a target: guessing costs a download
        f"watch this: {ID} please",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch",  # no video, and no collection either
        "https://www.youtube.com/playlist",  # playlist path, no list=
        "https://www.youtube.com/playlist?list=",
        f"https://youtu.be/{ID}/extra",
        f"https://www.youtube.com/embed/{ID}",  # not one of the accepted forms
        f"ftp://youtube.com/watch?v={ID}",
        "https://notyoutube.com/@handle",
        "https://www.youtube.com/@",  # a handle sigil with no handle
    ],
)
def test_targets_that_name_nothing_are_bad_requests(target):
    with pytest.raises(sources.BadRequest):
        sources.resolve(target)


def test_canonical_url_is_the_deep_link_form():
    assert sources.canonical_url(ID) == URL


# ----------------------------------------------------------- sources: collections


@pytest.mark.parametrize(
    "target",
    [
        "https://www.youtube.com/playlist?list=PLtestfixture01",
        "https://youtube.com/playlist?list=PL123&si=x",
        "https://www.youtube.com/@fixturechannel",
        "https://www.youtube.com/@fixturechannel/videos",
        "https://www.youtube.com/@fixturechannel/streams",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos",
        "https://www.youtube.com/c/FixtureChannel",
        "https://www.youtube.com/c/FixtureChannel/streams",
        "https://www.youtube.com/user/fixtureuser",
        "https://m.youtube.com/@fixturechannel",
    ],
)
def test_collection_forms_resolve_to_a_url(target):
    kind, value = sources.resolve(target)
    assert kind == sources.COLLECTION
    assert value == target


def test_a_scheme_less_collection_gets_one_for_the_lister():
    assert sources.resolve("youtube.com/@fixturechannel") == (
        sources.COLLECTION,
        "https://youtube.com/@fixturechannel",
    )


def test_video_id_refuses_a_collection_and_says_so():
    with pytest.raises(sources.BadRequest, match="playlist or channel"):
        sources.video_id("https://www.youtube.com/playlist?list=PL1")


def test_lister_output_is_ordered_deduplicated_and_filtered():
    out = f"{ID}\nplainvide00\n\n{ID}\nnot-an-id\n  another11ch  \nNA\n"
    assert sources.video_ids(out) == [ID, "plainvide00", "another11ch"]


def test_empty_lister_output_is_no_ids():
    assert sources.video_ids("") == []


# --------------------------------------------------------------------- the seams


def test_each_seam_reads_its_own_key(home):
    config(home, '[ingest]\nfetcher_command = "F"\nlister_command = "L"\n')
    assert fetch.fetcher(home) == "F"
    assert fetch.lister(home) == "L"


@pytest.mark.parametrize(
    "body", ["", "# nothing\n", "[ingest]\n", '[ingest]\nfetcher_command = "  "\n', "not toml ["]
)
def test_a_missing_or_empty_fetcher_is_a_config_error(home, body):
    config(home, body)
    with pytest.raises(fetch.ConfigError, match="fetcher"):
        fetch.fetcher(home)


def test_a_missing_lister_names_the_lister(home):
    config(home, '[ingest]\nfetcher_command = "F"\n')
    with pytest.raises(fetch.ConfigError, match="lister"):
        fetch.lister(home)


def test_no_config_file_at_all_is_a_config_error(home):
    with pytest.raises(fetch.ConfigError):
        fetch.fetcher(home)


def test_the_default_fetcher_carries_lesson_0001():
    command = fetch.DEFAULT_FETCHER_COMMAND
    assert "--no-playlist" in command and "--write-info-json" in command
    assert 'bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b' in command
    assert "$TAPEDECK_DEST/video.%(ext)s" in command and "$TAPEDECK_VIDEO_URL" in command


def test_the_default_lister_prints_flat_ids():
    command = fetch.DEFAULT_LISTER_COMMAND
    assert "--flat-playlist" in command and "%(id)s" in command
    assert "$TAPEDECK_COLLECTION_URL" in command


def test_the_fetcher_seam_receives_its_environment(home, staging):
    seen = '"$TAPEDECK_VIDEO_ID" "$TAPEDECK_VIDEO_URL" "$TAPEDECK_HOME"'
    fetch.run(f"printf '%s %s %s' {seen} > env.txt", home, ID, URL, staging)
    # cwd is the staging dir, so a relative write lands there and nowhere near the library
    assert (staging / "env.txt").read_text() == f"{ID} {URL} {home}"


def test_a_non_zero_fetcher_raises(home, staging):
    with pytest.raises(fetch.FetchError, match="exited 3"):
        fetch.run("exit 3", home, ID, URL, staging)


def test_the_lister_seam_receives_the_collection_url_and_returns_stdout(home):
    out = fetch.collect('printf "%s\\n" "$TAPEDECK_COLLECTION_URL"', home, "https://c/1")
    assert out == "https://c/1\n"


def test_a_non_zero_lister_raises_rather_than_returning_half_a_channel(home):
    with pytest.raises(fetch.FetchError, match="exited 1"):
        fetch.collect(f"printf '{ID}\\n'; exit 1", home, "https://c/1")


# --------------------------------------------------------- staging and discovery


def test_videos_ignores_sidecars_and_part_files(staging):
    for name in ("video.mp4", "video.info.json", "video.mp4.part", "video.webp", "other.mp4"):
        (staging / name).write_bytes(b"x")
    assert [p.name for p in fetch.videos(staging)] == ["video.mp4"]
    assert fetch.has_video(staging)


def test_no_video_is_a_fetch_error(staging):
    (staging / "video.info.json").write_text("{}")
    assert not fetch.has_video(staging)
    with pytest.raises(fetch.FetchError, match="no video file"):
        fetch.find_video(staging, ID)


@pytest.mark.parametrize("name", ["info.json", "video.info.json"])
def test_either_info_json_spelling_is_read(staging, name):
    (staging / name).write_text(json.dumps(INFO))
    assert fetch.read_info(staging, ID)["id"] == ID


def test_a_missing_info_json_names_the_problem(staging):
    (staging / "video.mp4").write_bytes(b"x")
    with pytest.raises(fetch.FetchError, match="info.json"):
        fetch.read_info(staging, ID)


def test_unreadable_info_json_is_a_fetch_error(staging):
    (staging / "info.json").write_text("{not json")
    with pytest.raises(fetch.FetchError, match="not readable JSON"):
        fetch.read_info(staging, ID)


# -------------------------------------------------------------------- meta.json


def validate(document, schema=SCHEMA):
    """Enough of JSON Schema for this one contract: required, additionalProperties,
    types, patterns, minima. Keeps the test honest without a dependency."""
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
    }
    assert isinstance(document, types[schema["type"]]), document
    if schema["type"] == "array":
        for item in document:
            validate(item, schema["items"])
        return
    for key in schema.get("required", []):
        assert key in document, f"missing required {key}"
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        assert not set(document) - set(properties), set(document) - set(properties)
    for key, value in document.items():
        rule = properties[key]
        assert isinstance(value, types[rule["type"]]), (key, value)
        if isinstance(value, bool):
            raise AssertionError(f"{key} is a bool, not a number")
        if "pattern" in rule:
            assert re.fullmatch(rule["pattern"], value), (key, value)
        if "minLength" in rule:
            assert len(value) >= rule["minLength"], (key, value)
        if "minimum" in rule:
            assert value >= rule["minimum"], (key, value)
        if rule["type"] == "array":
            validate(value, rule)


def test_normalized_meta_validates_and_keeps_only_the_schemas_keys():
    document = meta.normalize(ID, URL, INFO)
    validate(document)
    assert document["title"] == "Test Video: Building Things"  # whitespace tidied
    assert document["channel"] == "Fixture Channel"
    assert document["upload_date"] == "2026-01-15"
    assert document["duration_s"] == 720  # 719.64 rounded to whole seconds
    assert document["url"] == URL
    assert document["description"] == "Line one.\n\nLine two."
    assert document["chapters"] == [  # sorted by time, end_time dropped
        {"title": "Intro", "start_s": 0},
        {"title": "The Core Idea", "start_s": 95},
    ]
    assert document["ingested_at"].startswith("20")


def test_the_id_is_ours_not_the_fetchers():
    document = meta.normalize(ID, URL, {**INFO, "id": "somethingelse"})
    assert document["id"] == ID


def test_a_bare_minimum_info_still_validates():
    document = meta.normalize(ID, URL, {})
    validate(document)
    assert document["title"] == ID  # a titleless source is not a stranded video
    assert document["channel"] == ""
    assert document["duration_s"] == 0
    assert document["url"] == URL
    assert document["upload_date"] == document["ingested_at"][:10]
    assert "chapters" not in document and "description" not in document


@pytest.mark.parametrize(
    "info,expected",
    [
        ({"upload_date": "20260115"}, "2026-01-15"),
        ({"upload_date": "2026-01-15T10:00:00Z"}, "2026-01-15"),
        ({"upload_date": "unknown", "release_date": "20260202"}, "2026-02-02"),
        # a number is not a date string, and neither is junk: both fall back
        ({"upload_date": 20260115}, "2026-08-13"),
        ({"upload_date": "sometime"}, "2026-08-13"),
    ],
)
def test_dates_normalize_to_iso_or_fall_back_to_the_stamp(info, expected):
    document = meta.normalize(ID, URL, info, ingested_at="2026-08-13T00:00:00+00:00")
    assert document["upload_date"] == expected
    validate(document)


def test_junk_chapters_are_dropped_not_stored():
    info = {"chapters": ["not a dict", {"title": "No time"}, {"start_time": -5, "title": "Neg"}]}
    assert meta.normalize(ID, URL, info)["chapters"] == [{"title": "Neg", "start_s": 0}]


def test_fractional_chapter_starts_survive():
    info = {"chapters": [{"title": "Half", "start_time": 12.5}]}
    document = meta.normalize(ID, URL, info)
    assert document["chapters"] == [{"title": "Half", "start_s": 12.5}]
    validate(document)


def test_a_non_object_info_is_bad_meta():
    with pytest.raises(meta.BadMeta):
        meta.normalize(ID, URL, ["not", "an", "object"])


def test_meta_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    meta.write(tmp_path, meta.normalize(ID, URL, INFO))
    assert json.loads((tmp_path / "meta.json").read_text())["id"] == ID
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]


# -------------------------------------------------------------- install and add


def test_install_replaces_a_stale_container_and_keeps_the_transcript(home, staging):
    entry = home / "library" / ID
    entry.mkdir(parents=True)
    (entry / "video.mkv").write_bytes(b"old")
    (entry / "transcript.json").write_text('{"segments": []}')
    (staging / "video.mp4").write_bytes(b"new")
    install(entry, staging / "video.mp4", meta.normalize(ID, URL, INFO))
    assert [p.name for p in fetch.videos(entry)] == ["video.mp4"]
    assert (entry / "transcript.json").is_file()  # transcribe's file, not ours


def test_install_removes_an_entry_it_created_but_could_not_finish(home, staging):
    entry = home / "library" / ID
    with pytest.raises(OSError):  # the video vanished between fetch and move
        install(entry, staging / "gone.mp4", meta.normalize(ID, URL, INFO))
    assert not entry.exists()


FETCH_OK = """
printf 'bytes' > "$TAPEDECK_DEST/video.mp4"
printf '%s' '{"id": "ID", "title": "T", "duration": 12}' > "$TAPEDECK_DEST/info.json"
""".replace("ID", ID)


def test_add_writes_only_the_two_files_it_owns(home, capsys):
    config(home, f'[ingest]\nfetcher_command = "{script(home, "f.sh", FETCH_OK)}"\n')
    assert add(home, URL, force=False) == 0
    entry = home / "library" / ID
    assert sorted(p.name for p in entry.iterdir()) == ["meta.json", "video.mp4"]
    assert capsys.readouterr().out.strip() == str(entry)  # stdout: the entry, alone


def test_add_skips_an_existing_entry_and_force_refetches(home, capsys):
    counter = home / "count"
    body = f'echo run >> "{counter}"\n{FETCH_OK}'
    config(home, f'[ingest]\nfetcher_command = "{script(home, "f.sh", body)}"\n')
    assert add(home, ID, force=False) == 0
    assert add(home, ID, force=False) == 0
    assert counter.read_text().count("run") == 1
    assert add(home, ID, force=True) == 0
    assert counter.read_text().count("run") == 2


def test_a_failed_fetch_leaves_neither_entry_nor_staging_behind(home, monkeypatch):
    used = []

    def remember():
        used.append(real_stage())
        return used[-1]

    monkeypatch.setattr(fetch, "stage", remember)
    config(home, f'[ingest]\nfetcher_command = "{script(home, "f.sh", "exit 1")}"\n')
    with pytest.raises(fetch.FetchError):
        add(home, ID, force=False)
    assert list((home / "library").iterdir()) == []
    assert used and not used[0].exists(), "the scratch directory must be swept up too"


def test_add_refuses_a_collection_before_reading_any_seam(home):
    # no config at all: the collection must be refused on its own terms
    with pytest.raises(sources.BadRequest, match="playlist or channel"):
        add(home, "https://www.youtube.com/playlist?list=PL1", force=False)


# ------------------------------------------------------------------------ expand


def test_expand_of_a_video_prints_the_id_without_a_seam(home, capsys):
    assert expand(home, f"https://youtu.be/{ID}") == 0
    assert capsys.readouterr().out == f"{ID}\n"


def set_lister(home, body):
    config(home, f'[ingest]\nlister_command = "{script(home, "l.sh", body)}"\n')


def test_expand_of_a_collection_runs_the_lister(home, capsys):
    set_lister(home, f"printf '%s\\n' {ID} {ID} plainvide00 nope")
    assert expand(home, "https://www.youtube.com/@fixturechannel") == 0
    assert capsys.readouterr().out == f"{ID}\nplainvide00\n"


def test_expand_passes_the_collection_url_through_the_seam(home, capsys):
    set_lister(home, 'printf "%s\\n" "$TAPEDECK_COLLECTION_URL" > "$TAPEDECK_HOME/asked"')
    assert expand(home, "youtube.com/c/FixtureChannel") == 0
    assert (home / "asked").read_text() == "https://youtube.com/c/FixtureChannel\n"


def test_expand_of_an_empty_collection_prints_nothing_and_succeeds(home, capsys):
    set_lister(home, "exit 0")
    assert expand(home, "https://www.youtube.com/@empty") == 0
    assert capsys.readouterr().out == ""


def test_expand_of_a_failed_lister_raises_before_printing(home, capsys):
    set_lister(home, f"printf '{ID}\\n'\nexit 1")
    with pytest.raises(fetch.FetchError):
        expand(home, "https://www.youtube.com/@fixturechannel")
    assert capsys.readouterr().out == ""


def test_expand_of_garbage_is_a_bad_request(home):
    with pytest.raises(sources.BadRequest):
        expand(home, "https://example.com/nope")
