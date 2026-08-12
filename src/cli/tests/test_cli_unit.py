"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/cli/ are the real contract.
Run with: uv run --with pytest pytest src/cli/tests -q
"""

import json
import shlex
import sys
import tomllib

import pytest

import cli.components as components
import cli.library as library
import cli.main as main_mod
from cli.home import CONFIG_NAME, CONFIG_TEMPLATE, ensure, home_dir
from cli.main import build_parser, entry_id, main

META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video: Building Things",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "chapters": [{"title": "Intro", "start_s": 0}],
}
OTHER = {
    "id": "plainvide00",
    "title": "Sourdough Basics",
    "channel": "Bread",
    "upload_date": "2026-02-02",
    "duration_s": 600,
    "url": "https://www.youtube.com/watch?v=plainvide00",
}


@pytest.fixture
def home(tmp_path):
    return ensure(tmp_path / "home")


def add_entry(home, meta, transcript=False, archived=False, video="video.mp4"):
    entry = home / "library" / meta["id"]
    entry.mkdir(parents=True, exist_ok=True)
    if video:
        (entry / video).write_bytes(b"\x00fixture")
    (entry / "meta.json").write_text(json.dumps(meta))
    if transcript:
        (entry / "transcript.json").write_text("{}")
    if archived:
        (home / "archive" / f"{meta['id']}.md").write_text("---\n")
    return entry


# --- the home and the config it owns ----------------------------------------


def test_config_template_is_valid_toml_carrying_every_seam():
    config = tomllib.loads(CONFIG_TEMPLATE)
    assert "yt-dlp" in config["ingest"]["fetcher_command"]
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"]
    assert "claude" in config["ask"]["answerer_command"]


def test_seam_defaults_are_live_values_not_commented_out(home):
    """A fresh install can `add` immediately: the defaults parse as settings."""
    config = tomllib.loads((home / CONFIG_NAME).read_text())
    assert "$TAPEDECK_DEST" in config["ingest"]["fetcher_command"]
    assert "$TAPEDECK_OUT" in config["transcribe"]["transcriber_command"]


def test_ensure_scaffolds_a_home_that_does_not_exist_yet(tmp_path):
    home = ensure(tmp_path / "deep" / "deck")
    assert (home / "library").is_dir()
    assert (home / "archive").is_dir()
    assert (home / CONFIG_NAME).is_file()


def test_ensure_never_rewrites_an_existing_config(home):
    (home / CONFIG_NAME).write_text("[ingest]\nfetcher_command = 'mine'\n")
    ensure(home)
    assert (home / CONFIG_NAME).read_text() == "[ingest]\nfetcher_command = 'mine'\n"


def test_ensure_is_idempotent(home):
    before = (home / CONFIG_NAME).read_text()
    ensure(home)
    assert (home / CONFIG_NAME).read_text() == before


def test_home_dir_reads_the_environment_every_time(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "a"))
    assert home_dir() == tmp_path / "a"
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "b"))
    assert home_dir() == tmp_path / "b"


def test_home_dir_falls_back_to_the_default_and_expands_it(monkeypatch):
    monkeypatch.delenv("TAPEDECK_HOME", raising=False)
    assert "~" not in str(home_dir())


def test_home_dir_treats_an_empty_env_var_as_unset(monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", "")
    assert str(home_dir()).endswith("/dev/storage/tapedeck")


# --- the component seam ------------------------------------------------------


def test_invocation_defaults_to_running_the_module(monkeypatch):
    monkeypatch.delenv("TAPEDECK_INDEX_CMD", raising=False)
    assert components.invocation("index") == [sys.executable, "-m", "index"]


def test_invocation_prefers_a_per_component_override(monkeypatch):
    monkeypatch.setenv("TAPEDECK_INDEX_CMD", "sh -c 'echo hi'")
    assert components.invocation("index") == ["sh", "-c", "echo hi"]


def test_invocation_refuses_a_component_that_is_not_installed(monkeypatch):
    monkeypatch.delenv("TAPEDECK_NOSUCH_CMD", raising=False)
    with pytest.raises(components.RunError):
        components.invocation("nosuch")


def probe(monkeypatch, script):
    monkeypatch.setenv(
        "TAPEDECK_PROBE_CMD", f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    )


def test_run_hands_the_component_the_resolved_home(home, monkeypatch, capsys):
    probe(monkeypatch, "import os, sys; sys.stdout.write(os.environ['TAPEDECK_HOME'])")
    code, out = components.run("probe", [], home, capture=True)
    assert (code, out) == (0, str(home))
    # captured output is never dropped — it becomes progress
    assert str(home) in capsys.readouterr().err


def test_run_passes_the_verb_and_its_arguments_through(home, monkeypatch):
    probe(monkeypatch, "import sys; sys.stdout.write('|'.join(sys.argv[1:]))")
    assert components.run("probe", ["render", "dQw4w9WgXcQ"], home, capture=True)[1] == (
        "render|dQw4w9WgXcQ"
    )


def test_run_returns_the_component_exit_code(home, monkeypatch):
    probe(monkeypatch, "raise SystemExit(2)")
    assert components.run("probe", [], home, capture=True)[0] == 2


# --- reading the library -----------------------------------------------------


def test_entries_are_newest_upload_first(home):
    add_entry(home, META)
    add_entry(home, OTHER)
    assert [meta["id"] for meta in library.entries(home)] == ["plainvide00", "dQw4w9WgXcQ"]


def test_entries_skip_a_fetch_in_flight(home):
    add_entry(home, META)
    (home / "library" / ".dQw4w9WgXcQ.tmp.partial").mkdir()
    (home / "library" / "halfingest0").mkdir()  # no meta.json yet
    assert [meta["id"] for meta in library.entries(home)] == ["dQw4w9WgXcQ"]


def test_entries_step_over_an_unreadable_entry(home, capsys):
    add_entry(home, META)
    broken = home / "library" / "brokenmeta0"
    broken.mkdir()
    (broken / "meta.json").write_text("{not json")
    assert [meta["id"] for meta in library.entries(home)] == ["dQw4w9WgXcQ"]
    assert "brokenmeta0" in capsys.readouterr().err


def test_entries_on_an_empty_library_is_empty(home):
    assert library.entries(home) == []


def test_listing_carries_id_date_channel_and_title():
    line = library.listing([META])
    for field in ("dQw4w9WgXcQ", "2026-01-15", "Fixture Channel", "Test Video: Building Things"):
        assert field in line
    assert line.index("dQw4w9WgXcQ") < line.index("2026-01-15") < line.index("Fixture Channel")


def test_listing_aligns_rows_into_columns():
    lines = library.listing([META, OTHER]).splitlines()
    assert len(lines) == 2
    assert all(line.index("2026") == lines[0].index("2026") for line in lines)


def test_locate_reports_the_artifacts_that_are_there(home):
    add_entry(home, META, transcript=True, archived=True)
    meta, paths, missing = library.locate(home, "dQw4w9WgXcQ")
    assert meta["channel"] == "Fixture Channel"
    assert paths["video"].endswith("video.mp4")
    assert missing == []


def test_locate_names_the_archive_path_even_when_it_is_missing(home):
    add_entry(home, META)
    _, paths, missing = library.locate(home, "dQw4w9WgXcQ")
    assert paths["archive"] == str(home / "archive" / "dQw4w9WgXcQ.md")
    assert set(missing) == {"transcript", "archive"}


def test_locate_refuses_a_stranger(home):
    with pytest.raises(library.NotInLibrary):
        library.locate(home, "nosuchvid00")


def test_locate_refuses_something_that_is_not_an_id(home):
    with pytest.raises(library.NotInLibrary):
        library.locate(home, "not-a-video-id-at-all")


def test_locate_surfaces_a_corrupt_entry_as_a_failure(home):
    entry = home / "library" / "dQw4w9WgXcQ"
    entry.mkdir(parents=True)
    (entry / "meta.json").write_text("[]")
    with pytest.raises(library.Unreadable):
        library.locate(home, "dQw4w9WgXcQ")


def test_detail_shows_where_a_missing_transcript_would_live(home):
    add_entry(home, META)
    text = library.detail(*library.locate(home, "dQw4w9WgXcQ"))
    assert "Fixture Channel · 2026-01-15 · 0:12:00" in text
    assert "transcript.json" in text and "(missing)" in text


def test_hms_survives_metadata_without_a_duration():
    assert library.hms(None) == "0:00:00"
    assert library.hms(3661) == "1:01:01"


# --- the verbs ---------------------------------------------------------------


def parse(argv):
    return build_parser().parse_args(argv)


def record(monkeypatch, codes=()):
    """Stand in for the components, remembering how each was called."""
    calls = []
    replies = list(codes)

    def fake_run(module, args, home, capture=False):
        calls.append((module, args))
        code = replies.pop(0) if replies else 0
        out = str(home / "library" / "dQw4w9WgXcQ") if module == "ingest" else ""
        return code, out

    monkeypatch.setattr(components, "run", fake_run)
    return calls


def test_add_walks_the_derivation_chain_in_order(home, monkeypatch, capsys):
    calls = record(monkeypatch)
    assert main_mod.add(home, parse(["add", "https://youtu.be/dQw4w9WgXcQ"])) == 0
    assert [module for module, _ in calls] == ["ingest", "transcribe", "archive", "index"]
    assert [args[0] for _, args in calls] == ["add", "run", "render", "update"]
    assert capsys.readouterr().out.strip() == str(home / "archive" / "dQw4w9WgXcQ.md")


def test_add_stops_at_the_first_refusal_and_keeps_its_code(home, monkeypatch):
    calls = record(monkeypatch, codes=[2])
    assert main_mod.add(home, parse(["add", "https://example.com/nope"])) == 2
    assert [module for module, _ in calls] == ["ingest"]


def test_add_stops_when_a_later_step_fails(home, monkeypatch):
    calls = record(monkeypatch, codes=[0, 1])
    assert main_mod.add(home, parse(["add", "dQw4w9WgXcQ"])) == 1
    assert [module for module, _ in calls] == ["ingest", "transcribe"]


def test_add_forces_only_the_steps_that_skip_by_default(home, monkeypatch):
    calls = record(monkeypatch)
    main_mod.add(home, parse(["add", "dQw4w9WgXcQ", "--force"]))
    forced = {module for module, args in calls if "--force" in args}
    assert forced == {"ingest", "transcribe"}


def test_add_without_force_never_mentions_it(home, monkeypatch):
    calls = record(monkeypatch)
    main_mod.add(home, parse(["add", "dQw4w9WgXcQ"]))
    assert not any("--force" in args for _, args in calls)


def test_entry_id_reads_back_the_entry_ingest_wrote():
    assert entry_id("fetching…\n/tmp/deck/library/dQw4w9WgXcQ\n") == "dQw4w9WgXcQ"


def test_entry_id_refuses_to_guess_when_ingest_says_nothing():
    for reported in ("", "\n", "/tmp/deck/library/short"):
        with pytest.raises(components.RunError):
            entry_id(reported)


def test_search_forwards_k_and_json_and_guards_the_query(home, monkeypatch):
    calls = record(monkeypatch)
    main_mod.search(home, parse(["search", "-k", "3", "--json", "regeneration"]))
    module, args = calls[0]
    assert module == "index"
    assert args[:2] == ["search", "-k"] and args[2] == "3"
    assert "--json" in args
    assert args[-2:] == ["--", "regeneration"]


def test_search_keeps_a_multi_word_query_whole(home, monkeypatch):
    calls = record(monkeypatch)
    main_mod.search(home, parse(["search", "core", "idea"]))
    assert calls[0][1][-2:] == ["core", "idea"]


def test_ask_asks_the_ask_component_for_k_sources(home, monkeypatch):
    calls = record(monkeypatch)
    main_mod.ask(home, parse(["ask", "-k", "2", "what", "is", "regeneration"]))
    assert calls[0][0] == "ask"
    assert calls[0][1] == ["answer", "-k", "2", "--", "what", "is", "regeneration"]


def test_reindex_is_the_index_component(home, monkeypatch):
    calls = record(monkeypatch)
    assert main_mod.reindex(home, parse(["reindex"])) == 0
    assert calls == [("index", ["reindex"])]


def test_list_json_is_one_object_per_video(home, capsys):
    add_entry(home, META)
    assert main_mod.show_all(home, parse(["list", "--json"])) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == "dQw4w9WgXcQ"
    assert rows[0]["channel"] == "Fixture Channel"


def test_list_on_an_empty_library_succeeds_quietly(home, capsys):
    assert main_mod.show_all(home, parse(["list"])) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "nothing in the library" in captured.err


def test_show_json_carries_the_metadata_and_the_paths(home, capsys):
    add_entry(home, META, transcript=True)
    assert main_mod.show_one(home, parse(["show", "dQw4w9WgXcQ", "--json"])) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["title"] == "Test Video: Building Things"
    assert entry["paths"]["archive"].endswith("archive/dQw4w9WgXcQ.md")
    assert entry["missing"] == ["archive"]


# --- the executable ----------------------------------------------------------


def test_every_contract_verb_is_exposed():
    for verb in ("add", "search", "ask", "list", "show", "reindex"):
        assert verb in main_mod.VERBS
    assert len(main_mod.VERBS) == 6, "a seventh verb is a durable change (SPEC-cli-001)"


def test_no_verb_at_all_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args([])
    assert exit_info.value.code == 2


def test_an_unknown_verb_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["bogus"])
    assert exit_info.value.code == 2


def test_a_non_numeric_k_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["search", "-k", "many", "thing"])
    assert exit_info.value.code == 2


def test_main_scaffolds_the_home_before_any_verb_runs(tmp_path, monkeypatch, capsys):
    home = tmp_path / "unborn"
    monkeypatch.setenv("TAPEDECK_HOME", str(home))
    assert main(["list"]) == 0
    assert (home / "config.toml").is_file()
    capsys.readouterr()


def test_main_turns_a_missing_video_into_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    assert main(["show", "nosuchvid00"]) == 2
    assert "not in the library" in capsys.readouterr().err


def test_main_turns_an_unrunnable_component_into_exit_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))

    def boom(*args, **kwargs):
        raise components.RunError("the ask component is not installed")

    monkeypatch.setattr(components, "run", boom)
    assert main(["ask", "why"]) == 1
    assert "error:" in capsys.readouterr().err
