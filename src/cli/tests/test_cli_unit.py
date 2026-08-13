"""Ephemeral unit tests for the cli component (disposable, not durable evals).

These poke at the pieces the durable suite only sees through the executable:
argument translation, the first-run scaffold's content, and the small library
readers. Anything about end-to-end behaviour belongs in system/evals/cli/.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli import components, home, library  # noqa: E402
from cli.main import build_parser, dispatch, flag, option  # noqa: E402


@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    return home.resolve()


def entry_with(deck, video_id, meta=None, model="fixture/whisper-0", page=True):
    where = home.entry(deck, video_id)
    where.mkdir(parents=True, exist_ok=True)
    (where / "video.mp4").write_bytes(b"\x00media")
    (where / "meta.json").write_text(
        json.dumps(
            meta
            or {
                "id": video_id,
                "title": f"Title {video_id}",
                "channel": "Fixture Channel",
                "upload_date": "2026-01-15",
                "duration_s": 720,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    )
    if model:
        (where / "transcript.json").write_text(
            json.dumps({"video_id": video_id, "model": model, "segments": []})
        )
    if page:
        home.page(deck, video_id).write_text(f"# {video_id}\n")
    return where


# ---------------------------------------------------------------- the scaffold


def test_first_run_config_is_valid_toml_with_every_seam(deck):
    config = tomllib.loads((deck / "config.toml").read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "--flat-playlist" in config["ingest"]["lister_command"]
    assert "large-v3-turbo" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert config["ask"]["librarian_command"].startswith("claude -p")
    assert config["ask"]["answerer_command"].startswith("claude -p")


def test_scaffold_makes_the_home_whole_and_never_overwrites(deck):
    assert (deck / "library").is_dir() and (deck / "archive").is_dir()
    (deck / "config.toml").write_text("# mine now\n")
    (deck / "CLAUDE.md").write_text("# mine too\n")
    assert home.resolve() == deck
    assert (deck / "config.toml").read_text() == "# mine now\n"
    assert (deck / "CLAUDE.md").read_text() == "# mine too\n"


def test_a_command_with_a_quote_stays_valid_toml(monkeypatch):
    quoted = "sh -c 'echo hi'"
    assert tomllib.loads(f"c = {home.toml_value(quoted)}")["c"] == quoted
    plain = 'yt-dlp -f "bv*+ba"'
    assert tomllib.loads(f"c = {home.toml_value(plain)}")["c"] == plain


# --------------------------------------------------------- argument transation


def test_option_and_flag_pass_nothing_on_by_default():
    assert option("-k", None) == [] and option("-k", 5) == ["-k", "5"]
    assert flag(False, "--fast") == [] and flag(True, "--fast") == ["--fast"]


def delegated(monkeypatch):
    seen = {}

    def fake(module, args, home_dir):
        seen["call"] = (module, args)
        return 0

    monkeypatch.setattr(components, "delegate", fake)
    return seen


def parse(argv):
    return build_parser().parse_args(argv)


def test_ask_passes_video_scope_through(monkeypatch, deck):
    seen = delegated(monkeypatch)
    dispatch(parse(["ask", "what", "happened", "--video", "dQw4w9WgXcQ"]), deck)
    module, args = seen["call"]
    assert module == "ask"
    assert args == ["answer", "what", "happened", "--video", "dQw4w9WgXcQ"]


def test_ask_passes_k_and_fast_only_when_given(monkeypatch, deck):
    seen = delegated(monkeypatch)
    dispatch(parse(["ask", "why", "--fast", "-k", "3"]), deck)
    assert seen["call"][1] == ["answer", "why", "-k", "3", "--fast"]
    dispatch(parse(["ask", "why"]), deck)
    assert seen["call"][1] == ["answer", "why"]


def test_search_forwards_query_words_and_json(monkeypatch, deck):
    seen = delegated(monkeypatch)
    dispatch(parse(["search", "core", "idea", "--json"]), deck)
    assert seen["call"] == ("index", ["search", "core", "idea", "--json"])


def test_adapt_parakeet_is_transcribes_filter(monkeypatch, deck):
    seen = delegated(monkeypatch)
    dispatch(parse(["adapt-parakeet"]), deck)
    assert seen["call"] == ("transcribe", ["from-parakeet"])


def test_unknown_verb_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        parse(["bogus"])
    assert exit_info.value.code == 2


# ------------------------------------------------------------------- the library


def test_entries_ignores_dotted_and_non_directories(deck):
    entry_with(deck, "dQw4w9WgXcQ")
    (deck / "library" / ".tapedeck-tmp").mkdir()
    (deck / "library" / "stray.txt").write_text("x")
    assert home.entries(deck) == ["dQw4w9WgXcQ"]


def test_catalogue_is_newest_first_and_skips_unreadable(deck, capsys):
    entry_with(deck, "dQw4w9WgXcQ")
    entry_with(
        deck,
        "plainvide00",
        meta={
            "id": "plainvide00",
            "title": "Later",
            "channel": "Bread",
            "upload_date": "2026-02-02",
            "duration_s": 60,
            "url": "u",
        },
    )
    broken = home.entry(deck, "brokenvid00")
    broken.mkdir()
    (broken / "meta.json").write_text("{not json")
    rows = library.catalogue(deck)
    assert [row["id"] for row in rows] == ["plainvide00", "dQw4w9WgXcQ"]
    assert "brokenvid00" in capsys.readouterr().err


def test_show_rejects_an_unknown_id_with_2(deck, capsys):
    assert library.show(deck, "nosuchvid00", as_json=False) == 2
    assert "not in the library" in capsys.readouterr().err
    assert library.show(deck, "short", as_json=False) == 2


def test_show_json_carries_the_derived_paths(deck, capsys):
    entry_with(deck, "dQw4w9WgXcQ")
    assert library.show(deck, "dQw4w9WgXcQ", as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["archive"].endswith("dQw4w9WgXcQ.md")
    assert payload["media"].endswith("video.mp4")
    assert payload["transcript"].endswith("transcript.json")


def test_media_only_keeps_everything_derived(deck):
    where = entry_with(deck, "dQw4w9WgXcQ")
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=True) == 0
    assert not (where / "video.mp4").exists()
    assert (where / "transcript.json").is_file()
    assert home.page(deck, "dQw4w9WgXcQ").is_file()


def test_media_only_is_idempotent(deck):
    entry_with(deck, "dQw4w9WgXcQ")
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=True) == 0
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=True) == 0


def test_remove_unknown_id_is_2(deck):
    assert library.remove(deck, "nosuchvid00", media_only=False) == 2


def test_remove_still_works_when_only_the_page_survives(deck, monkeypatch):
    monkeypatch.setattr(components, "run", lambda *a, **k: _Ok())
    home.page(deck, "dQw4w9WgXcQ").write_text("# orphan\n")
    assert library.remove(deck, "dQw4w9WgXcQ", media_only=False) == 0
    assert not home.page(deck, "dQw4w9WgXcQ").exists()


class _Ok:
    returncode = 0
    stdout = ""


# --------------------------------------------------------------- orchestration


def test_add_refuses_force_on_a_collection(deck, capsys):
    code = components.add(deck, "https://www.youtube.com/@fixture", force=True)
    assert code == 2
    assert "--force" in capsys.readouterr().err


def test_add_refuses_a_target_that_is_neither(deck, capsys):
    assert components.add(deck, "https://example.com/nope", force=False) == 2
    assert "error:" in capsys.readouterr().err


def test_label_reads_the_model_or_none(deck):
    entry_with(deck, "dQw4w9WgXcQ", model="fixture/whisper-7")
    assert components.label(deck, "dQw4w9WgXcQ") == "fixture/whisper-7"
    entry_with(deck, "plainvide00", model=None)
    assert components.label(deck, "plainvide00") is None


def test_retranscribe_dry_run_lists_only_superseded(deck, capsys):
    (deck / "config.toml").write_text(
        '[transcribe]\ntranscriber_command = "true"\nmodel = "fixture/whisper-2"\n'
    )
    entry_with(deck, "dQw4w9WgXcQ", model="fixture/whisper-0")
    entry_with(deck, "plainvide00", model="fixture/whisper-2")
    assert components.retranscribe(deck, dry_run=True) == 0
    assert capsys.readouterr().out.split() == ["dQw4w9WgXcQ"]


def test_retranscribe_without_a_configured_model_is_a_usage_error(deck, capsys):
    (deck / "config.toml").write_text("[transcribe]\n")
    assert components.retranscribe(deck, dry_run=True) == 2
    assert "error:" in capsys.readouterr().err


def test_last_line_is_the_path_ingest_printed():
    assert components.last_line("noise\n/deck/library/dQw4w9WgXcQ\n\n").endswith("dQw4w9WgXcQ")
    assert components.last_line("") == ""
