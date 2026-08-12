"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/cli/ are the real contract.
Run with: uv run --with pytest pytest src/cli/tests -q
"""

import argparse
import json
import tomllib

import pytest

import cli.components as components
import cli.home as home_module
import cli.library as library
from cli import Failure
from cli.main import main, parser

META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video: Building Things",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}
OLDER = {**META, "id": "plainvide00", "title": "Sourdough Basics", "upload_date": "2026-01-01"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return home_module.prepare(home_module.resolve())


def add_entry(home, meta, transcript=True, page=True):
    entry = home / "library" / meta["id"]
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "video.mp4").write_bytes(b"\x00")
    (entry / "meta.json").write_text(json.dumps(meta))
    if transcript:
        (entry / "transcript.json").write_text('{"segments": []}')
    if page:
        (home / "archive" / f"{meta['id']}.md").write_text("# page\n")
    return entry


class Recorder:
    """Stands in for the component processes: records argv, replays exit codes."""

    def __init__(self, codes=None, stdout=""):
        self.calls, self.codes, self.stdout = [], codes or {}, stdout

    def __call__(self, module, args, home, capture=False):
        self.calls.append((module, args))
        out = self.stdout if module == "ingest" else ""
        return components.Result(self.codes.get(module, 0), out)


# --- home resolution and first-run scaffolding -------------------------------


def test_resolve_prefers_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    assert home_module.resolve() == tmp_path / "deck"


def test_resolve_falls_back_to_the_default_and_is_absolute(monkeypatch):
    monkeypatch.delenv("TAPEDECK_HOME", raising=False)
    resolved = home_module.resolve()
    assert resolved.is_absolute() and resolved.name == "tapedeck"


def test_resolve_expands_a_relative_home(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAPEDECK_HOME", "deck")
    assert home_module.resolve().is_absolute()


def test_prepare_scaffolds_directories_and_a_usable_config(home):
    assert (home / "library").is_dir() and (home / "archive").is_dir()
    config = tomllib.loads((home / "config.toml").read_text())
    assert "yt-dlp" in config["ingest"]["fetcher_command"]
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"]
    assert config["ask"]["answerer_command"] == "claude -p"


def test_prepare_never_rewrites_an_edited_config(home):
    (home / "config.toml").write_text('[ingest]\nfetcher_command = "mine"\n')
    home_module.prepare(home)
    assert (home / "config.toml").read_text() == '[ingest]\nfetcher_command = "mine"\n'


def test_prepare_reports_a_home_it_cannot_create(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    with pytest.raises(Failure) as exc:
        home_module.prepare(blocked / "deck")
    assert exc.value.code == 1


# --- component delegation ----------------------------------------------------


def test_command_defaults_to_this_interpreter(monkeypatch):
    monkeypatch.delenv("TAPEDECK_INGEST_CMD", raising=False)
    assert components.command("ingest")[-2:] == ["-m", "ingest"]


def test_command_honours_the_harness_override(monkeypatch):
    monkeypatch.setenv("TAPEDECK_INGEST_CMD", "fake ingest --flag")
    assert components.command("ingest") == ["fake", "ingest", "--flag"]


def test_run_captures_stdout_and_names_the_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_ARCHIVE_CMD", "sh -c 'echo $TAPEDECK_HOME'")
    result = components.run("archive", [], tmp_path, capture=True)
    assert result.code == 0 and result.stdout.strip() == str(tmp_path)


def test_run_reports_a_component_it_cannot_start(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_INDEX_CMD", str(tmp_path / "nope"))
    with pytest.raises(Failure):
        components.run("index", [], tmp_path)


@pytest.mark.parametrize("raw, expected", [(0, 0), (1, 1), (2, 2), (-9, 1), (127, 1)])
def test_only_contract_exit_codes_survive(raw, expected):
    assert components.exit_code(raw) == expected


# --- reading the library -----------------------------------------------------


def test_records_are_newest_first_and_skip_non_entries(home):
    add_entry(home, META)
    add_entry(home, OLDER)
    (home / "library" / ".dQw4w9WgXcQ.tmp.partial").mkdir()
    (home / "library" / "halfway1234").mkdir()  # fetched, no meta.json yet
    found = library.records(home)
    assert [r["id"] for r in found] == ["dQw4w9WgXcQ", "plainvide00"]
    assert found[0]["archive"] and found[0]["transcript"]


def test_a_damaged_entry_does_not_break_the_listing(home, capsys):
    add_entry(home, META)
    broken = home / "library" / "brokenmeta0"
    broken.mkdir()
    (broken / "meta.json").write_text("{not json")
    assert [r["id"] for r in library.records(home)] == ["dQw4w9WgXcQ"]
    assert "brokenmeta0" in capsys.readouterr().err


def test_listing_carries_id_date_channel_and_title(home):
    add_entry(home, META)
    line = library.listing(library.records(home))
    for field in ("dQw4w9WgXcQ", "2026-01-15", "Fixture Channel", "Test Video: Building Things"):
        assert field in line


def test_detail_shows_undone_derivation_honestly(home):
    add_entry(home, META, transcript=False, page=False)
    text = library.detail(library.one(home, "dQw4w9WgXcQ"))
    assert "not transcribed yet" in text and "not rendered yet" in text
    assert "0:12:00" in text and "Fixture Channel" in text


def test_one_rejects_a_bad_id_and_a_missing_video(home):
    for bad in ("nope", "nosuchvid00"):
        with pytest.raises(Failure) as exc:
            library.one(home, bad)
        assert exc.value.code == 2


def test_ingested_id_reads_the_entry_ingest_printed():
    assert library.ingested_id("/deck/library/dQw4w9WgXcQ\n") == "dQw4w9WgXcQ"
    assert library.ingested_id("noise\n/deck/library/dQw4w9WgXcQ\n") == "dQw4w9WgXcQ"


@pytest.mark.parametrize("stdout", ["", "\n", "/deck/library/short"])
def test_ingested_id_refuses_to_guess(stdout):
    with pytest.raises(Failure):
        library.ingested_id(stdout)


def test_hms_formats_hours_minutes_seconds():
    assert (library.hms(0), library.hms(720), library.hms(3725)) == ("0:00:00", "0:12:00", "1:02:05")


# --- the verb surface --------------------------------------------------------


def test_the_surface_is_exactly_six_verbs():
    sub = next(a for a in parser()._actions if isinstance(a, argparse._SubParsersAction))
    assert set(sub.choices) == {"add", "search", "ask", "list", "show", "reindex"}


def test_unknown_verb_and_missing_verb_exit_2(capsys):
    for argv in (["bogus"], []):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
    capsys.readouterr()


def test_add_walks_the_chain_in_order(home, monkeypatch, capsys):
    add_entry(home, META, transcript=False, page=False)
    recorder = Recorder(stdout=str(home / "library" / "dQw4w9WgXcQ"))
    monkeypatch.setattr(components, "run", recorder)
    assert main(["add", "https://youtu.be/dQw4w9WgXcQ"]) == 0
    assert [module for module, _ in recorder.calls] == ["ingest", "transcribe", "archive", "index"]
    assert recorder.calls[1][1] == ["run", "dQw4w9WgXcQ"]
    assert recorder.calls[3][1] == ["update", "dQw4w9WgXcQ"]
    assert "archive/dQw4w9WgXcQ.md" in capsys.readouterr().out


def test_force_reaches_the_two_expensive_steps(home, monkeypatch):
    recorder = Recorder(stdout=str(home / "library" / "dQw4w9WgXcQ"))
    monkeypatch.setattr(components, "run", recorder)
    main(["add", "dQw4w9WgXcQ", "--force"])
    assert recorder.calls[0][1] == ["add", "dQw4w9WgXcQ", "--force"]
    assert recorder.calls[1][1] == ["run", "dQw4w9WgXcQ", "--force"]
    assert all("--force" not in args for _, args in recorder.calls[2:])


def test_a_failed_link_stops_the_chain_with_its_own_code(home, monkeypatch):
    recorder = Recorder(codes={"ingest": 2})
    monkeypatch.setattr(components, "run", recorder)
    assert main(["add", "https://example.com/nope"]) == 2
    assert [module for module, _ in recorder.calls] == ["ingest"]


def test_a_transcribe_failure_never_renders_a_page(home, monkeypatch):
    recorder = Recorder(codes={"transcribe": 1}, stdout=str(home / "library" / "dQw4w9WgXcQ"))
    monkeypatch.setattr(components, "run", recorder)
    assert main(["add", "dQw4w9WgXcQ"]) == 1
    assert [module for module, _ in recorder.calls] == ["ingest", "transcribe"]


def test_search_and_ask_are_delegated_with_flags(home, monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(components, "run", recorder)
    main(["search", "the", "core", "idea", "--json", "-k", "3"])
    main(["ask", "what is the core idea"])
    assert recorder.calls[0] == ("index", ["search", "--json", "-k", "3", "--", "the", "core", "idea"])
    assert recorder.calls[1] == ("ask", ["run", "--", "what is the core idea"])


def test_reindex_is_delegated_to_index(home, monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(components, "run", recorder)
    assert main(["reindex"]) == 0
    assert recorder.calls == [("index", ["reindex"])]


def test_a_component_failure_becomes_our_exit_code(home, monkeypatch):
    monkeypatch.setattr(components, "run", Recorder(codes={"index": 1}))
    assert main(["search", "anything"]) == 1


def test_list_and_show_speak_json(home, capsys):
    add_entry(home, META)
    assert main(["list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["id"] == "dQw4w9WgXcQ" and listed[0]["archive"].endswith(".md")
    assert main(["show", "dQw4w9WgXcQ", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["channel"] == "Fixture Channel"


def test_an_empty_library_lists_nothing_on_stdout(home, capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr()
    assert out.out == "" and "add" in out.err
    assert main(["list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_show_reports_a_video_that_is_not_here(home, capsys):
    assert main(["show", "nosuchvid00"]) == 2
    assert "not in the library" in capsys.readouterr().err


def test_a_first_run_scaffolds_before_the_verb(tmp_path, monkeypatch, capsys):
    fresh = tmp_path / "fresh" / "deck"
    monkeypatch.setenv("TAPEDECK_HOME", str(fresh))
    assert main(["list"]) == 0
    assert (fresh / "config.toml").is_file() and (fresh / "library").is_dir()
