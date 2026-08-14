"""Ephemeral unit tests for the cli's own decisions.

The durable evaluations drive the installed executable; these poke the parts that
are cheaper to interrogate directly — the scaffolded config, what a sweep decides
to skip, and how a failing step maps onto an exit code — with the component
subprocesses replaced by recorders.
"""

from __future__ import annotations

import json
import tomllib

import pytest

from cli import components, home, library, main, pipeline, views


@pytest.fixture
def deck(tmp_path):
    return home.scaffold(tmp_path / "deck")


@pytest.fixture
def calls(monkeypatch):
    """Every component invocation, recorded instead of run. `views` holds its own
    reference to `quietly`, so both names are replaced."""
    seen = []

    def fake(home_path, module, args):
        seen.append((module, *args))
        return 0

    monkeypatch.setattr(components, "quietly", fake)
    monkeypatch.setattr(views, "quietly", fake)
    return seen


def add_entry(deck, video_id, *, media=True, meta=True, transcript=True, page=True, model="m/1"):
    entry = deck / "library" / video_id
    entry.mkdir(parents=True, exist_ok=True)
    if media:
        (entry / "video.mp4").write_bytes(b"bytes")
    if meta:
        (entry / "meta.json").write_text(
            json.dumps(
                {
                    "id": video_id,
                    "title": f"Video {video_id}",
                    "channel": "Fixture Channel",
                    "upload_date": "2026-01-15",
                    "duration_s": 720,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        )
    if transcript:
        (entry / "transcript.json").write_text(
            json.dumps({"video_id": video_id, "model": model, "segments": []})
        )
    if page:
        (deck / "archive" / f"{video_id}.md").write_text("# page\n")
    return entry


# --- first run ---------------------------------------------------------------


def test_scaffold_writes_a_config_that_parses_as_toml(deck):
    config = tomllib.loads((deck / "config.toml").read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "$TAPEDECK_COLLECTION_URL" in config["ingest"]["lister_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert "librarian_command" in config["ask"] and "answerer_command" in config["ask"]


def test_scaffold_documents_the_parakeet_alternative_without_enabling_it(deck):
    text = (deck / "config.toml").read_text()
    config = tomllib.loads(text)
    assert "adapt-parakeet" in text, "the published alternative must be visible"
    assert "parakeet" not in config["transcribe"]["transcriber_command"]


def test_scaffold_writes_the_librarian_brief(deck):
    brief = (deck / "CLAUDE.md").read_text()
    assert "not in the library" in brief
    assert "cite" in brief.lower()


def test_scaffold_never_overwrites_what_is_there(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    (deck / "config.toml").write_text("# mine\n")
    (deck / "CLAUDE.md").write_text("# my brief\n")
    home.scaffold(deck)
    assert (deck / "config.toml").read_text() == "# mine\n"
    assert (deck / "CLAUDE.md").read_text() == "# my brief\n"


def test_toml_string_survives_a_command_with_quotes():
    command = "sh -c 'echo \"$TAPEDECK_OUT\"'"
    parsed = tomllib.loads(f"command = {home.toml_string(command)}")
    assert parsed["command"] == command


# --- what a sweep skips ------------------------------------------------------


def test_complete_needs_every_link(deck):
    add_entry(deck, "aaaaaaaaaaa")
    assert library.complete(deck, "aaaaaaaaaaa")
    for video_id, missing in (
        ("bbbbbbbbbbb", "page"),
        ("ccccccccccc", "transcript"),
        ("ddddddddddd", "meta"),
        ("eeeeeeeeeee", "media"),
    ):
        add_entry(deck, video_id, **{missing: False})
        assert not library.complete(deck, video_id), missing


def test_a_partial_download_is_not_media(deck):
    entry = add_entry(deck, "aaaaaaaaaaa")
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    assert library.media(deck, "aaaaaaaaaaa") is None
    assert not library.complete(deck, "aaaaaaaaaaa")


def test_sweep_derives_only_the_incomplete(deck, calls):
    add_entry(deck, "aaaaaaaaaaa")
    add_entry(deck, "bbbbbbbbbbb", page=False)
    assert pipeline.sweep(deck, ["aaaaaaaaaaa", "bbbbbbbbbbb"]) == 0
    assert [call for call in calls if call[0] == "ingest"] == [("ingest", "add", "bbbbbbbbbbb")]
    assert all("aaaaaaaaaaa" not in call for call in calls)


def test_sweep_survives_one_failure(deck, monkeypatch, capsys):
    def fake(home_path, module, args):
        return 1 if args[-1] == "bbbbbbbbbbb" else 0

    monkeypatch.setattr(components, "quietly", fake)
    assert pipeline.sweep(deck, ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]) == 1
    out = capsys.readouterr()
    assert "2 added, 0 already present, 1 failed" in out.out
    assert "bbbbbbbbbbb" in out.err


# --- retranscribe selection --------------------------------------------------


def test_superseded_picks_stale_labels_only(deck):
    add_entry(deck, "aaaaaaaaaaa", model="m/1")
    add_entry(deck, "bbbbbbbbbbb", model="m/2")
    redo, notes = pipeline.superseded(deck, "m/2")
    assert redo == ["aaaaaaaaaaa"]
    assert notes == []


def test_superseded_skips_what_it_could_never_re_derive(deck):
    add_entry(deck, "aaaaaaaaaaa", model="m/1")
    add_entry(deck, "bbbbbbbbbbb", media=False, model="m/1")
    (deck / "library" / "reading-notes").mkdir()
    redo, notes = pipeline.superseded(deck, "m/2")
    assert redo == ["aaaaaaaaaaa"]
    assert any("bbbbbbbbbbb" in note for note in notes)
    assert any("reading-notes" in note for note in notes)


def test_a_missing_transcript_is_not_the_configured_label(deck):
    add_entry(deck, "aaaaaaaaaaa", transcript=False)
    redo, _ = pipeline.superseded(deck, "m/2")
    assert redo == ["aaaaaaaaaaa"]


def test_retranscribe_forces_the_transcript_and_never_re_fetches(deck, calls):
    pipeline.rederive(deck, "aaaaaaaaaaa", force=True)
    assert calls == [
        ("transcribe", "run", "aaaaaaaaaaa", "--force"),
        ("archive", "render", "aaaaaaaaaaa"),
        ("index", "update", "aaaaaaaaaaa"),
    ]


# --- views -------------------------------------------------------------------


def test_show_reports_an_absent_video_without_naming_the_partial(deck, capsys):
    entry = add_entry(deck, "aaaaaaaaaaa")
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    assert views.show(deck, "aaaaaaaaaaa", as_json=False) == 0
    assert "video.part" not in capsys.readouterr().out
    assert views.show(deck, "aaaaaaaaaaa", as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["media"] is None


def test_show_unknown_id_is_a_usage_error(deck):
    with pytest.raises(components.Usage):
        views.show(deck, "nosuchvid00", as_json=False)
    with pytest.raises(components.Usage):
        views.show(deck, "not-an-id", as_json=False)


def test_list_is_newest_first_and_skips_unreadable_entries(deck, capsys):
    add_entry(deck, "aaaaaaaaaaa")
    entry = add_entry(deck, "bbbbbbbbbbb")
    meta = json.loads((entry / "meta.json").read_text())
    meta["upload_date"] = "2026-06-01"
    (entry / "meta.json").write_text(json.dumps(meta))
    add_entry(deck, "ccccccccccc", meta=False)
    assert views.list_videos(deck, as_json=True) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in rows] == ["bbbbbbbbbbb", "aaaaaaaaaaa"]


def test_rm_media_only_keeps_everything_else(deck, capsys):
    entry = add_entry(deck, "aaaaaaaaaaa")
    assert views.remove(deck, "aaaaaaaaaaa", media_only=True) == 0
    assert not (entry / "video.mp4").exists()
    assert (entry / "transcript.json").is_file() and (entry / "meta.json").is_file()
    assert (deck / "archive" / "aaaaaaaaaaa.md").is_file()


def test_rm_unknown_id_is_a_usage_error(deck):
    with pytest.raises(components.Usage):
        views.remove(deck, "nosuchvid00", media_only=False)


def test_rm_removes_the_entry_and_its_page(deck, calls):
    add_entry(deck, "aaaaaaaaaaa")
    assert views.remove(deck, "aaaaaaaaaaa", media_only=False) == 0
    assert not (deck / "library" / "aaaaaaaaaaa").exists()
    assert not (deck / "archive" / "aaaaaaaaaaa.md").exists()
    assert ("index", "update", "aaaaaaaaaaa") in calls


# --- the surface -------------------------------------------------------------


SUBCOMMANDS = (
    "add", "search", "ask", "list", "show", "reindex", "rm", "retranscribe", "adapt-parakeet",
)


def test_the_parser_carries_exactly_the_contract(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main.main(["--help"])
    assert exit_info.value.code == 0
    printed = capsys.readouterr().out
    for verb in SUBCOMMANDS:
        assert verb in printed


def test_unknown_verb_is_exit_2():
    with pytest.raises(SystemExit) as exit_info:
        main.main(["bogus"])
    assert exit_info.value.code == 2


def test_force_on_a_collection_is_a_usage_error(deck, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(deck))
    code = main.main(["add", "https://www.youtube.com/playlist?list=PLxx", "--force"])
    assert code == 2


def test_a_garbage_url_is_a_usage_error(deck, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(deck))
    assert main.main(["add", "https://example.com/nope"]) == 2


def test_a_failed_step_is_exit_1(deck, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(deck))
    monkeypatch.setattr(components, "quietly", lambda *args, **kwargs: 3)
    assert main.main(["add", "dQw4w9WgXcQ"]) == 1


def test_delegated_verbs_pass_the_component_its_arguments(deck, monkeypatch):
    seen = []

    def fake(home_path, module, args):
        seen.append((module, args))
        return 0

    monkeypatch.setenv("TAPEDECK_HOME", str(deck))
    monkeypatch.setattr(main, "passthrough", fake)
    assert main.main(["search", "-k", "3", "--json", "core idea"]) == 0
    assert seen[-1] == ("index", ["search", "-k", "3", "--json", "--", "core idea"])
    assert main.main(["ask", "what is it", "--fast", "--video", "dQw4w9WgXcQ"]) == 0
    assert seen[-1] == ("ask", ["run", "--fast", "--video", "dQw4w9WgXcQ", "--", "what is it"])
    assert main.main(["adapt-parakeet"]) == 0
    assert seen[-1] == ("transcribe", ["from-parakeet"])
    assert main.main(["reindex"]) == 0
    assert seen[-1] == ("index", ["reindex"])
