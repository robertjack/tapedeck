"""Ephemeral unit tests for ingest — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the address grammar,
info.json normalization against the real schema file, and the commit rules that
protect neighbouring components' files.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from ingest import fetch, meta  # noqa: E402
from ingest.sources import Unrecognized, canonical_id  # noqa: E402

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "system/contracts/meta.schema.json").read_text()
)
ID = "dQw4w9WgXcQ"
INFO = {
    "id": ID,
    "title": "Test Video: Building Things",
    "uploader": "Fixture Channel",
    "upload_date": "20260115",
    "duration": 720.4,
    "webpage_url": f"https://www.youtube.com/watch?v={ID}",
    "description": "A fixture.",
    "chapters": [{"title": "Intro", "start_time": 0}, {"title": "Core", "start_time": 95.5}],
    "_filename": "junk we must not carry through",
}


def check_schema(doc):
    """Enough of meta.schema.json to catch a drifting normalizer, no dependency."""
    props = SCHEMA["properties"]
    for key in SCHEMA["required"]:
        assert key in doc, f"missing required {key}"
    for key, value in doc.items():
        spec = props.get(key)
        assert spec is not None, f"additionalProperties: false forbids {key}"
        kinds = {"string": str, "integer": int, "number": (int, float), "array": list}
        assert isinstance(value, kinds[spec["type"]]), f"{key} is not {spec['type']}"
        if "pattern" in spec:
            assert re.fullmatch(spec["pattern"], value), f"{key}={value!r} fails its pattern"


# --- addresses ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"https://www.youtube.com/watch?v={ID}&t=42s",
        f"http://youtube.com/watch?app=desktop&v={ID}",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://music.youtube.com/watch?v={ID}",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=30",
        f"youtu.be/{ID}",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://www.youtube.com/embed/{ID}",
        f"https://www.youtube.com/live/{ID}",
        f"  {ID}  ",
    ],
)
def test_every_address_form_resolves(text):
    assert canonical_id(text) == ID


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "https://example.com/not-a-video",
        f"https://vimeo.com/watch?v={ID}",
        f"https://notyoutube.com/watch?v={ID}",
        "https://www.youtube.com/watch?v=too-short",
        "https://www.youtube.com/results?search_query=cats",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/shorts/",
        "short",
        "this is not a url at all",
    ],
)
def test_non_video_addresses_are_rejected(text):
    with pytest.raises(Unrecognized):
        canonical_id(text)


# --- normalization -----------------------------------------------------------


def test_normalize_matches_the_schema_and_drops_unknown_fields():
    doc = meta.normalize(ID, INFO)
    check_schema(doc)
    assert doc["upload_date"] == "2026-01-15"
    assert doc["duration_s"] == 720
    assert doc["channel"] == "Fixture Channel"
    assert doc["chapters"] == [{"title": "Intro", "start_s": 0}, {"title": "Core", "start_s": 95.5}]
    assert "_filename" not in doc
    assert list(doc)[:6] == SCHEMA["required"]


def test_sparse_info_still_yields_a_valid_document():
    doc = meta.normalize(ID, {"timestamp": 1767225600, "duration": None})
    check_schema(doc)
    assert doc["title"] == ID  # a titleless source is still addressable
    assert doc["channel"] == ""
    assert doc["duration_s"] == 0
    assert doc["url"] == f"https://www.youtube.com/watch?v={ID}"
    assert "chapters" not in doc and "description" not in doc


def test_undateable_info_is_bad_metadata():
    with pytest.raises(meta.BadMetadata):
        meta.normalize(ID, {"title": "x", "upload_date": "not-a-date"})


def test_unplaceable_chapters_are_dropped_not_guessed():
    doc = meta.normalize(ID, {**INFO, "chapters": [{"title": "a"}, {"title": "b", "start_time": -2}]})
    assert doc["chapters"] == [{"title": "b", "start_s": 0}]


def test_yt_dlp_named_info_json_is_found(tmp_path):
    (tmp_path / "video.info.json").write_text(json.dumps(INFO))
    assert meta.read_info(meta.find_info(tmp_path))["title"] == INFO["title"]
    with pytest.raises(meta.BadMetadata):
        meta.find_info(tmp_path / "nowhere")


def test_unparseable_info_json_is_bad_metadata(tmp_path):
    (tmp_path / "info.json").write_text("[not, an, object")
    with pytest.raises(meta.BadMetadata):
        meta.read_info(meta.find_info(tmp_path))


# --- the seam and the commit -------------------------------------------------


def test_fetcher_command_requires_the_section(tmp_path):
    (tmp_path / "config.toml").write_text("[transcribe]\nmodel = 'x'\n")
    with pytest.raises(fetch.ConfigError, match="fetcher"):
        fetch.fetcher_command(tmp_path)
    (tmp_path / "config.toml").write_text("[ingest]\nfetcher_command = ''\n")
    with pytest.raises(fetch.ConfigError, match="fetcher"):
        fetch.fetcher_command(tmp_path)
    (tmp_path / "config.toml").write_text("[ingest\nbroken = ")
    with pytest.raises(fetch.ConfigError):
        fetch.fetcher_command(tmp_path)
    (tmp_path / "config.toml").write_text("[ingest]\nfetcher_command = 'sh f.sh'\n")
    assert fetch.fetcher_command(tmp_path) == "sh f.sh"


def stage_with(tmp_path, names):
    staging = fetch.stage(tmp_path / "library", ID)
    for name in names:
        (staging / name).write_text(name)
    return staging


def test_commit_of_a_new_entry_keeps_only_owned_files(tmp_path):
    staging = stage_with(tmp_path, ["video.mp4", "meta.json", "info.json", "video.mp4.part"])
    entry = fetch.commit(staging, tmp_path / "library" / ID)
    assert sorted(p.name for p in entry.iterdir()) == ["meta.json", "video.mp4"]
    assert not staging.exists()
    assert [p.name for p in (tmp_path / "library").iterdir()] == [ID]


def test_commit_over_an_existing_entry_spares_the_transcript(tmp_path):
    entry = tmp_path / "library" / ID
    entry.mkdir(parents=True)
    (entry / "video.webm").write_text("old")  # a different extension than the re-fetch
    (entry / "meta.json").write_text("{}")
    (entry / "transcript.json").write_text("transcribe owns this")
    staging = stage_with(tmp_path, ["video.mp4", "meta.json", "info.json"])
    fetch.commit(staging, entry)
    assert sorted(p.name for p in entry.iterdir()) == ["meta.json", "transcript.json", "video.mp4"]
    assert (entry / "transcript.json").read_text() == "transcribe owns this"
    assert not staging.exists()


def test_find_video_ignores_the_fetchers_leftovers(tmp_path):
    staging = stage_with(tmp_path, ["info.json", "video.mp4.part", "video.f137.mp4"])
    with pytest.raises(fetch.FetchError):
        fetch.find_video(staging)
    (staging / "video.mkv").write_text("real")
    assert fetch.find_video(staging).name == "video.mkv"
