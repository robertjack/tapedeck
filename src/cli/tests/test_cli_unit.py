"""Ephemeral unit tests for the cli component — disposable, unlike system/evals.

These cover the seams the durable evals reach only indirectly: the argument
forwarding the cli does on behalf of other components (including the `--` guard
against queries that start with a dash), home scaffolding, and the library
reading and removal helpers.
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli import home as home_mod  # noqa: E402
from cli import library, main  # noqa: E402
from cli.components import ComponentError, command  # noqa: E402

# --- the `--` guard, checked against argparse itself rather than against belief --


def component_parser():
    """The shape every component's parser has: verb, then positionals and flags."""
    parser = argparse.ArgumentParser(prog="component")
    sub = parser.add_subparsers(dest="verb", required=True)
    many = sub.add_parser("search")
    many.add_argument("query", nargs="+")
    many.add_argument("-k", type=int, default=8)
    many.add_argument("--json", action="store_true")
    one = sub.add_parser("update")
    one.add_argument("video_id")
    one.add_argument("--force", action="store_true")
    return parser


def test_dash_dash_survives_a_nargs_plus_positional():
    args = component_parser().parse_args(["search", "-k", "5", "--json", "--", "fixture query"])
    assert args.query == ["fixture query"]
    assert args.k == 5 and args.json is True


def test_dash_dash_protects_a_query_that_looks_like_a_flag():
    assert component_parser().parse_args(["search", "--", "-k"]).query == ["-k"]


def test_dash_dash_with_a_single_positional():
    args = component_parser().parse_args(["update", "--force", "--", "dQw4w9WgXcQ"])
    assert args.video_id == "dQw4w9WgXcQ" and args.force is True


# --- what the cli hands each component ------------------------------------------

PAGE = "archive/dQw4w9WgXcQ.md"
ENTRY = "library/dQw4w9WgXcQ"


@pytest.fixture
def calls(monkeypatch):
    """Record every component invocation instead of running one."""
    seen = []

    def fake_step(module, args, home):
        seen.append((module, args))
        return {"ingest": ENTRY, "archive": PAGE}.get(module, "")

    monkeypatch.setattr(main, "step", fake_step)
    monkeypatch.setattr(main, "delegate", lambda m, a, h: seen.append((m, a)) or 0)
    return seen


def parse(argv):
    return main.build_parser().parse_args(argv)


def test_add_drives_the_pipeline_in_order(tmp_path, calls):
    assert main.add(tmp_path, parse(["add", "https://youtu.be/dQw4w9WgXcQ"])) == 0
    assert [module for module, _ in calls] == ["ingest", "transcribe", "archive", "index"]
    assert calls[0] == ("ingest", ["add", "--", "https://youtu.be/dQw4w9WgXcQ"])
    assert calls[3] == ("index", ["update", "--", "dQw4w9WgXcQ"])


def test_add_forwards_force_to_the_expensive_steps(tmp_path, calls):
    main.add(tmp_path, parse(["add", "dQw4w9WgXcQ", "--force"]))
    assert {module for module, args in calls if "--force" in args} == {"ingest", "transcribe"}


def test_add_refuses_an_ingest_that_names_no_video(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "step", lambda m, a, h: "")
    with pytest.raises(main.Failure):
        main.add(tmp_path, parse(["add", "dQw4w9WgXcQ"]))


def test_search_forwards_k_and_json_and_joins_the_query(tmp_path, calls):
    main.search(tmp_path, parse(["search", "the", "core", "idea", "-k", "3", "--json"]))
    assert calls == [("index", ["search", "-k", "3", "--json", "--", "the core idea"])]


def test_search_leaves_k_to_the_component_when_unset(tmp_path, calls):
    main.search(tmp_path, parse(["search", "bread"]))
    assert calls == [("index", ["search", "--", "bread"])]


def test_ask_forwards_the_question_whole(tmp_path, calls):
    main.ask(tmp_path, parse(["ask", "what", "is", "it", "-k", "2"]))
    assert calls == [("ask", ["run", "-k", "2", "--", "what is it"])]


def test_reindex_delegates(tmp_path, calls):
    main.reindex(tmp_path, parse(["reindex"]))
    assert calls == [("index", ["reindex"])]


def test_a_component_is_a_process_and_can_be_replaced(monkeypatch):
    assert command("ingest") == [sys.executable, "-m", "ingest"]
    monkeypatch.setenv("TAPEDECK_INGEST_CMD", "./bin/ingest --fast")
    assert command("ingest") == ["./bin/ingest", "--fast"]


# --- home scaffolding -----------------------------------------------------------


def test_resolve_prefers_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    assert home_mod.resolve() == tmp_path / "deck"


def test_resolve_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("TAPEDECK_HOME", raising=False)
    assert home_mod.resolve() == Path(home_mod.DEFAULT_HOME).expanduser()


def test_scaffold_creates_dirs_and_a_parsable_config(tmp_path):
    home = home_mod.scaffold(tmp_path / "fresh" / "deck")
    assert (home / "library").is_dir() and (home / "archive").is_dir()
    config = tomllib.loads((home / "config.toml").read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"]
    assert config["ask"]["answerer_command"] == "claude -p"


def test_scaffold_never_rewrites_an_existing_config(tmp_path):
    (tmp_path / "config.toml").write_text("# mine\n")
    home_mod.scaffold(tmp_path)
    assert (tmp_path / "config.toml").read_text() == "# mine\n"


# --- library reading ------------------------------------------------------------

META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}
OLDER = {**META, "id": "plainvide00", "title": "Sourdough", "upload_date": "2025-02-02"}


def build(home, *metas, media=True):
    (home / "archive").mkdir(parents=True, exist_ok=True)
    for meta in metas:
        entry = home / "library" / meta["id"]
        entry.mkdir(parents=True)
        (entry / "meta.json").write_text(json.dumps(meta))
        (entry / "transcript.json").write_text('{"segments": []}')
        if media:
            (entry / "video.mp4").write_bytes(b"0" * 2048)
        (home / "archive" / f"{meta['id']}.md").write_text("# page\n")
    return home


def test_videos_lists_newest_first(tmp_path):
    build(tmp_path, META, OLDER)
    assert [v["id"] for v in library.videos(tmp_path)] == ["dQw4w9WgXcQ", "plainvide00"]


def test_videos_skips_entries_without_metadata(tmp_path):
    build(tmp_path, META)
    (tmp_path / "library" / "halfdonevid").mkdir()
    (tmp_path / "library" / ".staging.partial").mkdir()
    assert [v["id"] for v in library.videos(tmp_path)] == ["dQw4w9WgXcQ"]


def test_videos_on_an_empty_home(tmp_path):
    assert library.videos(tmp_path) == []


def test_media_ignores_the_fetchers_leftovers(tmp_path):
    build(tmp_path, META)
    entry = tmp_path / "library" / META["id"]
    (entry / "video.info.json").write_text("{}")
    (entry / "video.mp4.part").write_bytes(b"0")
    assert [p.name for p in library.media(tmp_path, META["id"])] == ["video.mp4"]


def test_clock_and_size():
    assert library.clock(720) == "0:12:00"
    assert library.clock(3661) == "1:01:01"
    assert library.clock(None) == "?"
    assert library.size(512) == "512 B"
    assert library.size(2048) == "2.0 KB"


def test_list_and_show_render(tmp_path, capsys):
    build(tmp_path, META)
    assert main.show_list(tmp_path, parse(["list"])) == 0
    line = capsys.readouterr().out
    assert "dQw4w9WgXcQ" in line and "2026-01-15" in line and "Fixture Channel" in line
    assert main.show(tmp_path, parse(["show", "dQw4w9WgXcQ", "--json"])) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["channel"] == "Fixture Channel"
    assert shown["paths"]["archive"].endswith("archive/dQw4w9WgXcQ.md")
    assert shown["paths"]["media"].endswith("video.mp4")


def test_show_reports_missing_derived_artifacts_as_none(tmp_path, capsys):
    build(tmp_path, META, media=False)
    (tmp_path / "archive" / "dQw4w9WgXcQ.md").unlink()
    main.show(tmp_path, parse(["show", "dQw4w9WgXcQ", "--json"]))
    paths = json.loads(capsys.readouterr().out)["paths"]
    assert paths["media"] is None and paths["archive"] is None


# --- rm -------------------------------------------------------------------------


def test_rm_unknown_id_is_a_usage_error(tmp_path, calls):
    build(tmp_path, META)
    with pytest.raises(main.Failure) as caught:
        main.rm(tmp_path, parse(["rm", "nosuchvid00"]))
    assert caught.value.code == 2 and "nosuchvid00" in str(caught.value)
    assert calls == []


def test_rm_malformed_id_is_a_usage_error(tmp_path, calls):
    with pytest.raises(main.Failure) as caught:
        main.rm(tmp_path, parse(["rm", "../../etc"]))
    assert caught.value.code == 2


def test_rm_asks_the_index_to_catch_up_only_after_the_page_is_gone(tmp_path, monkeypatch):
    build(tmp_path, META)
    seen = []
    page = tmp_path / "archive" / "dQw4w9WgXcQ.md"
    entry = tmp_path / "library" / "dQw4w9WgXcQ"
    monkeypatch.setattr(
        main, "step", lambda m, a, h: seen.append((m, page.exists(), entry.is_dir())) or ""
    )
    assert main.rm(tmp_path, parse(["rm", "dQw4w9WgXcQ"])) == 0
    # index runs with the page already gone (so it drops the rows) and the entry
    # still there (so an interrupted rm is still recognisable and re-runnable)
    assert seen == [("index", False, True)]
    assert not entry.exists() and not page.exists()


def test_rm_stops_before_deleting_the_entry_if_the_index_fails(tmp_path, monkeypatch):
    build(tmp_path, META)
    monkeypatch.setattr(main, "step", _raiser(ComponentError("index broke", 1)))
    with pytest.raises(ComponentError):
        main.rm(tmp_path, parse(["rm", "dQw4w9WgXcQ"]))
    assert (tmp_path / "library" / "dQw4w9WgXcQ" / "video.mp4").is_file()


def test_rm_media_only_keeps_everything_derived(tmp_path, calls):
    build(tmp_path, META)
    assert main.rm(tmp_path, parse(["rm", "dQw4w9WgXcQ", "--media-only"])) == 0
    entry = tmp_path / "library" / "dQw4w9WgXcQ"
    assert not (entry / "video.mp4").exists()
    assert (entry / "meta.json").is_file() and (entry / "transcript.json").is_file()
    assert (tmp_path / "archive" / "dQw4w9WgXcQ.md").is_file()
    assert calls == [], "--media-only must not touch the index"


def test_rm_media_only_is_idempotent(tmp_path, calls):
    build(tmp_path, META, media=False)
    assert main.rm(tmp_path, parse(["rm", "dQw4w9WgXcQ", "--media-only"])) == 0


def test_rm_leaves_other_videos_alone(tmp_path, calls):
    build(tmp_path, META, OLDER)
    main.rm(tmp_path, parse(["rm", "dQw4w9WgXcQ"]))
    assert (tmp_path / "library" / "plainvide00" / "video.mp4").is_file()
    assert (tmp_path / "archive" / "plainvide00.md").is_file()


# --- exit codes -----------------------------------------------------------------


def _raiser(exc):
    def raise_it(*_args, **_kwargs):
        raise exc

    return raise_it


def test_component_failures_keep_their_exit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    for code in (1, 2):
        monkeypatch.setattr(main, "step", _raiser(ComponentError("nope", code)))
        assert main.main(["add", "dQw4w9WgXcQ"]) == code


def test_show_unknown_id_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    assert main.main(["show", "nosuchvid00"]) == 2


def test_unknown_verb_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    with pytest.raises(SystemExit) as caught:
        main.main(["bogus"])
    assert caught.value.code == 2


def test_every_contracted_verb_is_reachable():
    assert set(main.VERBS) == {"add", "search", "ask", "list", "show", "reindex", "rm"}
