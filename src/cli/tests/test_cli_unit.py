"""Ephemeral unit tests for cli — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the first-run scaffold's
exact content and its refusal to overwrite, the layout helpers the verbs share,
the catalogue's ordering and tolerance of a damaged entry, and — the new
surface — how a collection sweep counts and survives what happens to it
(SPEC-cli-003). The subprocess boundary to the other components is stubbed here;
the durable evals drive the real one.
"""

import json
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from cli import components, home, library  # noqa: E402

ID = "dQw4w9WgXcQ"
OTHER = "plainvide00"
PLAYLIST = "https://www.youtube.com/playlist?list=PLtest"
META = {
    "id": ID,
    "title": "Test Video",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": f"https://www.youtube.com/watch?v={ID}",
}


class Done:
    """What subprocess.run gives back, as much of it as the cli reads."""

    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    return home.resolve()


def entry(deck, video_id=ID, meta=META, transcript=True, video=True):
    where = home.entry(deck, video_id)
    where.mkdir(parents=True, exist_ok=True)
    if video:
        (where / "video.mp4").write_bytes(b"\x00fixture")
    if meta is not None:
        (where / "meta.json").write_text(json.dumps({**meta, "id": video_id}))
    if transcript:
        (where / "transcript.json").write_text('{"segments": []}')
    return where


# ---------------------------------------------------------------- the scaffold


def test_config_carries_every_seam_the_components_publish():
    config = tomllib.loads(home.config_text())
    assert set(config) == {"ingest", "transcribe", "ask"}
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "vcodec^=avc1" in config["ingest"]["fetcher_command"]  # LESSON-0001
    assert "--flat-playlist" in config["ingest"]["lister_command"]  # SPEC-cli-003
    assert "$TAPEDECK_COLLECTION_URL" in config["ingest"]["lister_command"]
    assert "large-v3-turbo" in config["transcribe"]["transcriber_command"]  # LESSON-0002
    assert "--condition-on-previous-text False" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert config["ask"]["librarian_command"].startswith("claude -p")
    assert config["ask"]["answerer_command"]


def test_toml_value_survives_a_command_with_a_quote_in_it():
    assert home.toml_value("say 'hi'") == '"say \'hi\'"'
    assert tomllib.loads(f"k = {home.toml_value('say \'hi\'')}")["k"] == "say 'hi'"


def test_first_run_creates_the_home_and_later_runs_leave_it_alone(deck):
    for name in home.DIRECTORIES:
        assert (deck / name).is_dir()
    assert "not in the library" in (deck / home.BRIEF_NAME).read_text()
    (deck / home.CONFIG_NAME).write_text("# mine now\n")
    assert home.resolve() == deck
    assert (deck / home.CONFIG_NAME).read_text() == "# mine now\n"


def test_home_follows_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "elsewhere"))
    assert home.resolve() == tmp_path / "elsewhere"


# ------------------------------------------------------------ layout helpers


def test_media_is_the_download_and_not_its_sidecars(deck):
    where = entry(deck)
    (where / "video.info.json").write_text("{}")
    assert [p.name for p in home.media(where)] == ["video.mp4"]
    assert home.ingested(deck, ID)


def test_ingested_needs_both_the_video_and_its_metadata(deck):
    entry(deck, video=False)
    assert not home.ingested(deck, ID)
    entry(deck, OTHER, meta=None)
    assert not home.ingested(deck, OTHER)
    assert not home.ingested(deck, "absentvid0")


def test_hms_never_raises_on_a_hand_edited_duration():
    assert library.hms(3725) == "1:02:05"
    assert library.hms(None) == ""
    assert library.hms("nonsense") == ""


# ------------------------------------------------------------- list and show


def test_catalogue_is_newest_first_and_forgives_a_damaged_entry(deck, capsys):
    entry(deck)
    entry(deck, OTHER, {**META, "upload_date": "2026-02-02", "title": "Sourdough"})
    (deck / home.LIBRARY / ".tmp-fetch").mkdir()
    broken = deck / home.LIBRARY / "brokenvid00"
    broken.mkdir()
    (broken / "meta.json").write_text("{not json")
    listed = library.catalogue(deck)
    assert [video["id"] for video in listed] == [OTHER, ID]
    assert "brokenvid00" in capsys.readouterr().err


def test_show_reports_an_unknown_id_as_a_usage_error(deck):
    assert library.show(deck, "nosuchvid00", as_json=False) == 2
    assert library.show(deck, "not-an-id", as_json=False) == 2


def test_show_json_names_the_derived_artifacts(deck, capsys):
    entry(deck)
    home.page(deck, ID).write_text("# page\n")
    assert library.show(deck, ID, as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "Test Video"
    assert payload["archive"].endswith(f"{ID}.md")
    assert payload["media"].endswith("video.mp4")


# ------------------------------------------------------------------ removal


def test_rm_media_only_keeps_everything_derived(deck):
    where = entry(deck)
    home.page(deck, ID).write_text("# page\n")
    assert library.remove(deck, ID, media_only=True) == 0
    assert not (where / "video.mp4").exists()
    assert (where / "transcript.json").is_file()
    assert home.page(deck, ID).is_file()


def test_rm_drops_the_page_and_asks_the_index_to_catch_up(deck, monkeypatch):
    entry(deck)
    entry(deck, OTHER)
    home.page(deck, ID).write_text("# page\n")
    seen = []

    def fake(module, args, where, capture=False):
        seen.append((module, args))
        return Done()

    monkeypatch.setattr(components, "run", fake)
    assert library.remove(deck, ID, media_only=False) == 0
    assert seen == [("index", ["update", ID])]  # the index rebuilds itself; cli never writes it
    assert not home.entry(deck, ID).exists()
    assert not home.page(deck, ID).exists()
    assert home.entry(deck, OTHER).is_dir()  # never another video's data


def test_rm_of_an_unknown_id_is_a_usage_error(deck):
    assert library.remove(deck, "nosuchvid00", media_only=False) == 2


# ------------------------------------------------------- add: one and many


def test_add_refuses_a_target_that_names_nothing(capsys):
    assert components.add(Path("/nowhere"), "https://example.com/nope", force=False) == 2
    assert "error:" in capsys.readouterr().err


def test_force_on_a_collection_is_a_usage_error(deck, monkeypatch, capsys):
    monkeypatch.setattr(components, "sweep", lambda *a: pytest.fail("no sweep may start"))
    assert components.add(deck, PLAYLIST, force=True) == 2
    assert "--force" in capsys.readouterr().err


def test_a_video_target_runs_the_pipeline_once(deck, monkeypatch):
    calls = []
    monkeypatch.setattr(
        components,
        "add_one",
        lambda where, target, force: calls.append((target, force)) or 0,
    )
    assert components.add(deck, f"https://youtu.be/{ID}", force=True) == 0
    assert calls == [(f"https://youtu.be/{ID}", True)]


def stub_expand(monkeypatch, ids, returncode=0):
    def fake(module, args, where, capture=False):
        assert (module, args[0]) == ("ingest", "expand")
        return Done(returncode, "\n".join([*ids, "NA", ""]))

    monkeypatch.setattr(components, "run", fake)


def test_sweep_adds_every_video_and_summarizes(deck, monkeypatch, capsys):
    stub_expand(monkeypatch, ["aaaaaaaaaaa", "bbbbbbbbbbb"])
    swept = []
    monkeypatch.setattr(
        components, "add_one", lambda where, vid, force: swept.append((vid, force)) or 0
    )
    assert components.add(deck, PLAYLIST, force=False) == 0
    assert swept == [("aaaaaaaaaaa", False), ("bbbbbbbbbbb", False)]
    assert "2 added, 0 already present, 0 failed" in capsys.readouterr().out


def test_sweep_counts_what_was_already_here(deck, monkeypatch, capsys):
    entry(deck, "aaaaaaaaaaa")
    stub_expand(monkeypatch, ["aaaaaaaaaaa", "bbbbbbbbbbb"])
    monkeypatch.setattr(components, "add_one", lambda where, vid, force: 0)
    assert components.add(deck, PLAYLIST, force=False) == 0
    assert "1 added, 1 already present, 0 failed" in capsys.readouterr().out


def test_sweep_goes_on_past_a_failure_and_fails_the_run(deck, monkeypatch, capsys):
    stub_expand(monkeypatch, ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
    swept = []
    monkeypatch.setattr(
        components,
        "add_one",
        lambda where, vid, force: swept.append(vid) or (1 if vid == "bbbbbbbbbbb" else 0),
    )
    assert components.add(deck, PLAYLIST, force=False) == 1
    assert swept == ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]
    out = capsys.readouterr()
    assert "bbbbbbbbbbb" in out.err
    assert "2 added, 0 already present, 1 failed" in out.out


def test_a_listing_that_failed_is_not_swept(deck, monkeypatch):
    stub_expand(monkeypatch, ["aaaaaaaaaaa"], returncode=1)
    monkeypatch.setattr(components, "add_one", lambda *a: pytest.fail("half a channel is not one"))
    assert components.add(deck, PLAYLIST, force=False) == 1


def test_an_empty_collection_is_not_a_failure(deck, monkeypatch, capsys):
    stub_expand(monkeypatch, [])
    assert components.add(deck, PLAYLIST, force=False) == 0
    assert "0 added, 0 already present, 0 failed" in capsys.readouterr().out


def test_add_one_stops_at_the_first_stage_that_fails(deck, monkeypatch, capsys):
    calls = []

    def fake(module, args, where, capture=False):
        calls.append(module)
        if module == "transcribe":
            return Done(1)
        return Done(0, f"{home.entry(deck, ID)}\n")

    monkeypatch.setattr(components, "run", fake)
    assert components.add_one(deck, ID, force=False) == 1
    assert calls == ["ingest", "transcribe"]


def test_add_one_forces_the_transcript_when_the_video_is_refetched(deck, monkeypatch, capsys):
    seen = []

    def fake(module, args, where, capture=False):
        seen.append((module, args))
        return Done(0, f"{home.entry(deck, ID)}\n")

    monkeypatch.setattr(components, "run", fake)
    assert components.add_one(deck, ID, force=True) == 0
    assert ("ingest", ["add", ID, "--force"]) in seen
    assert ("transcribe", ["run", ID, "--force"]) in seen
    assert ("archive", ["render", ID]) in seen
    assert ("index", ["update", ID]) in seen
    assert capsys.readouterr().out.strip().endswith(f"{ID}.md")


def test_add_one_needs_an_entry_it_can_build_on(deck, monkeypatch, capsys):
    monkeypatch.setattr(components, "run", lambda *a, **k: Done(0, "somewhere odd\n"))
    assert components.add_one(deck, ID, force=False) == 1
    assert "error:" in capsys.readouterr().err
