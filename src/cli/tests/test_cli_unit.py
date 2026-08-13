"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/cli/ are the real contract. These
cover the scaffold's content, the catalogue's edge cases, and the argument
plumbing between verbs and components without paying for a subprocess.

Run with: uv run --with pytest pytest src/cli/tests -q
"""

import json
import tomllib

import pytest

from cli import components, home, library
from cli.main import build_parser, dispatch, flag, limit, main

META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video: Building Things",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}
OTHER = {**META, "id": "plainvide00", "title": "Sourdough", "upload_date": "2026-02-02"}


@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    return home.resolve()


def entry(deck, meta, media=True, transcript=True):
    path = home.entry(deck, meta["id"])
    path.mkdir(parents=True, exist_ok=True)
    (path / "meta.json").write_text(json.dumps(meta))
    if media:
        (path / "video.mp4").write_bytes(b"\x00bytes")
    if transcript:
        (path / "transcript.json").write_text('{"segments": []}')
    home.page(deck, meta["id"]).write_text("# page\n")
    return path


class Recorder:
    """Stands in for components.run: records the boundary calls, never spawns."""

    def __init__(self, stdout="", codes=None):
        self.calls, self.stdout, self.codes = [], stdout, codes or {}

    def __call__(self, module, args, home_path, capture=False):
        self.calls.append((module, args))
        code = self.codes.get(module, 0)
        return type("Result", (), {"returncode": code, "stdout": self.stdout})()


# ---------------------------------------------------------------- the scaffold


def test_config_is_toml_carrying_every_seam(deck):
    config = tomllib.loads((deck / "config.toml").read_text())
    assert "yt-dlp" in config["ingest"]["fetcher_command"]
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"]
    assert "claude" in config["ask"]["librarian_command"]
    assert "claude" in config["ask"]["answerer_command"]


def test_scaffold_makes_the_home_whole(deck):
    assert (deck / "library").is_dir() and (deck / "archive").is_dir()
    brief = (deck / "CLAUDE.md").read_text()
    assert "not in the library" in brief and "cite" in brief.lower()


def test_scaffold_never_overwrites_an_edited_config(deck):
    (deck / "config.toml").write_text("[ingest]\nfetcher_command = 'mine'\n")
    (deck / "CLAUDE.md").write_text("my brief")
    assert home.resolve() == deck
    assert "mine" in (deck / "config.toml").read_text()
    assert (deck / "CLAUDE.md").read_text() == "my brief"


@pytest.mark.parametrize("raw", ['-o "$X/video.%(ext)s"', "it's -o 'x'", 'both " and \'', "a\nb"])
def test_toml_value_survives_any_quoting(raw):
    assert tomllib.loads("k = " + home.toml_value(raw))["k"] == raw


# ------------------------------------------------------------- list and show


def test_catalogue_is_newest_first_and_skips_what_is_not_a_video(deck, capsys):
    entry(deck, META)
    entry(deck, OTHER)
    (deck / "library" / ".dQw4w9WgXcQ.tmp.partial").mkdir()
    (deck / "library" / "brokenvid00").mkdir()
    (deck / "library" / "brokenvid00" / "meta.json").write_text("{not json")
    assert [video["id"] for video in library.catalogue(deck)] == ["plainvide00", "dQw4w9WgXcQ"]
    assert "brokenvid00" in capsys.readouterr().err


def test_list_json_mirrors_the_human_line(deck, capsys):
    entry(deck, META)
    assert library.show_all(deck, as_json=True) == 0
    assert json.loads(capsys.readouterr().out) == [
        {
            "id": "dQw4w9WgXcQ",
            "upload_date": "2026-01-15",
            "channel": "Fixture Channel",
            "title": "Test Video: Building Things",
        }
    ]


def test_empty_list_says_so_on_stderr_only(deck, capsys):
    assert library.show_all(deck, as_json=False) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "tapedeck add" in captured.err
    assert library.show_all(deck, as_json=True) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_show_reports_metadata_and_the_archive_path(deck, capsys):
    entry(deck, META)
    assert library.show(deck, "dQw4w9WgXcQ", as_json=False) == 0
    out = capsys.readouterr().out
    assert "Fixture Channel" in out and "0:12:00" in out
    assert str(home.page(deck, "dQw4w9WgXcQ")) in out


def test_show_json_adds_the_derived_paths(deck, capsys):
    path = entry(deck, META)
    assert library.show(deck, "dQw4w9WgXcQ", as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == META["title"]
    assert payload["archive"] == str(home.page(deck, "dQw4w9WgXcQ"))
    assert payload["media"] == str(path / "video.mp4")


def test_show_unknown_or_malformed_id_is_a_usage_error(deck):
    assert library.show(deck, "nosuchvid00", as_json=False) == 2
    assert library.show(deck, "nope", as_json=False) == 2


def test_show_unreadable_meta_is_an_operation_failure(deck):
    path = entry(deck, META)
    (path / "meta.json").write_text("{not json")
    assert library.show(deck, "dQw4w9WgXcQ", as_json=False) == 1


# ------------------------------------------------------------------- removal


def test_rm_deletes_the_entry_the_page_and_the_index_rows(deck, monkeypatch, capsys):
    entry(deck, META)
    entry(deck, OTHER)
    recorder = Recorder()
    monkeypatch.setattr(components, "run", recorder)
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=False) == 0
    assert recorder.calls == [("index", ["update", "dQw4w9WgXcQ"])]
    assert not home.entry(deck, "dQw4w9WgXcQ").exists()
    assert not home.page(deck, "dQw4w9WgXcQ").exists()
    assert home.entry(deck, "plainvide00").is_dir()
    assert home.page(deck, "plainvide00").is_file()
    assert "removed" in capsys.readouterr().out


def test_rm_reports_an_index_that_would_not_let_go(deck, monkeypatch):
    entry(deck, META)
    monkeypatch.setattr(components, "run", Recorder(codes={"index": 1}))
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=False) == 1


def test_rm_media_only_keeps_everything_derived(deck, monkeypatch):
    path = entry(deck, META)
    monkeypatch.setattr(components, "run", Recorder(codes={"index": 1}))  # never called
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=True) == 0
    assert not (path / "video.mp4").exists()
    assert (path / "meta.json").is_file() and (path / "transcript.json").is_file()
    assert home.page(deck, "dQw4w9WgXcQ").is_file()
    # and again: nothing left to reclaim is not a failure (SPEC-core-003)
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=True) == 0


def test_rm_unknown_id_is_a_usage_error(deck, capsys):
    assert library.remove(deck, "nosuchvid00", media_only=False) == 2
    assert "nosuchvid00" in capsys.readouterr().err
    assert library.remove(deck, "../../etc", media_only=False) == 2


def test_rm_works_from_a_dangling_archive_page(deck, monkeypatch):
    home.page(deck, "dQw4w9WgXcQ").write_text("# orphan\n")
    monkeypatch.setattr(components, "run", Recorder())
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=False) == 0
    assert not home.page(deck, "dQw4w9WgXcQ").exists()


def test_media_is_only_the_download(deck):
    path = entry(deck, META)
    (path / "video.json").write_text("{}")
    assert [p.name for p in library.media_files(path)] == ["video.mp4"]


# -------------------------------------------------------------- the pipeline


def test_add_runs_the_chain_in_order(deck, monkeypatch):
    recorder = Recorder(stdout=f"{home.entry(deck, 'dQw4w9WgXcQ')}\n")
    monkeypatch.setattr(components, "run", recorder)
    assert components.add(deck, "https://youtu.be/dQw4w9WgXcQ", force=False) == 0
    assert recorder.calls == [
        ("ingest", ["add", "https://youtu.be/dQw4w9WgXcQ"]),
        ("transcribe", ["run", "dQw4w9WgXcQ"]),
        ("archive", ["render", "dQw4w9WgXcQ"]),
        ("index", ["update", "dQw4w9WgXcQ"]),
    ]


def test_force_re_derives_the_transcript_too(deck, monkeypatch):
    recorder = Recorder(stdout=str(home.entry(deck, "dQw4w9WgXcQ")))
    monkeypatch.setattr(components, "run", recorder)
    assert components.add(deck, "dQw4w9WgXcQ", force=True) == 0
    assert recorder.calls[0] == ("ingest", ["add", "dQw4w9WgXcQ", "--force"])
    assert recorder.calls[1] == ("transcribe", ["run", "dQw4w9WgXcQ", "--force"])
    assert recorder.calls[2] == ("archive", ["render", "dQw4w9WgXcQ"])


@pytest.mark.parametrize("failing,code", [("ingest", 2), ("transcribe", 1), ("archive", 1)])
def test_a_broken_link_stops_the_chain_with_its_own_code(deck, monkeypatch, failing, code):
    recorder = Recorder(stdout=str(home.entry(deck, "dQw4w9WgXcQ")), codes={failing: code})
    monkeypatch.setattr(components, "run", recorder)
    assert components.add(deck, "dQw4w9WgXcQ", force=False) == code
    assert [module for module, _ in recorder.calls][-1] == failing


def test_an_ingest_that_names_no_entry_fails(deck, monkeypatch, capsys):
    monkeypatch.setattr(components, "run", Recorder(stdout="\n"))
    assert components.add(deck, "dQw4w9WgXcQ", force=False) == 1
    assert "error" in capsys.readouterr().err


def test_last_line_is_the_artifact_path():
    assert components.last_line("note\n/tmp/library/id\n") == "/tmp/library/id"
    assert components.last_line("  \n") == ""


# ------------------------------------------------------------------ the surface


def test_every_verb_parses_and_nothing_else_does():
    parser = build_parser()
    for argv in (["add", "x"], ["search", "q"], ["ask", "q"], ["list"], ["show", "i"],
                 ["reindex"], ["rm", "i"]):
        assert parser.parse_args(argv).verb == argv[0]
    for argv in ([], ["bogus"], ["add"], ["rm"]):
        with pytest.raises(SystemExit) as exit:
            parser.parse_args(argv)
        assert exit.value.code == 2


def test_help_names_every_verb(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    help_text = capsys.readouterr().out
    for verb in ("add", "search", "ask", "list", "show", "reindex", "rm"):
        assert verb in help_text


def test_optional_arguments_are_passed_on_only_when_given():
    assert limit(None) == [] and limit(4) == ["-k", "4"]
    assert flag(False, "--json") == [] and flag(True, "--json") == ["--json"]


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["search", "core", "idea"], ("index", ["search", "core", "idea"])),
        (["search", "q", "-k", "3", "--json"], ("index", ["search", "q", "-k", "3", "--json"])),
        (["ask", "why"], ("ask", ["answer", "why"])),
        (["ask", "why", "--fast", "-k", "2"], ("ask", ["answer", "why", "-k", "2", "--fast"])),
        (["reindex"], ("index", ["reindex"])),
    ],
)
def test_read_only_verbs_are_handed_over_whole(deck, monkeypatch, argv, expected):
    handed = []
    monkeypatch.setattr(
        components, "delegate", lambda module, args, home_path: handed.append((module, args)) or 7
    )
    assert dispatch(build_parser().parse_args(argv), deck) == 7
    assert handed == [expected]


def test_main_resolves_the_home_before_the_verb_runs(tmp_path, monkeypatch):
    fresh = tmp_path / "nested" / "deck"
    monkeypatch.setenv("TAPEDECK_HOME", str(fresh))
    assert main(["list"]) == 0
    assert (fresh / "config.toml").is_file()


def test_main_turns_a_broken_home_into_an_operation_failure(tmp_path, monkeypatch, capsys):
    blocked = tmp_path / "deck"
    blocked.write_text("not a directory")
    monkeypatch.setenv("TAPEDECK_HOME", str(blocked))
    assert main(["list"]) == 1
    assert "error" in capsys.readouterr().err
