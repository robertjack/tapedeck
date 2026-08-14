"""Ephemeral unit tests for the cli's pure parts.

The durable evaluations under system/evals/cli drive the executable; these poke
at the pieces that are awkward to reach from there — the TOML the scaffold
writes, the head-executable rule, the report's column, the wizard's remedy
lookup, the tour's length.
"""

import platform
import shlex
import sys
import tomllib

import pytest

from cli import Usage, doctor, home, setup, teach, views
from cli.main import build_parser

MISSING = "no-such-tool-in-this-test"


# --- home: the file the cli owns ---------------------------------------------


def test_config_text_is_valid_toml_with_every_seam():
    config = tomllib.loads(home.config_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert config["ingest"]["lister_command"].startswith("yt-dlp")
    assert config["transcribe"]["transcriber_command"].startswith("mlx_whisper")
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert config["ask"]["librarian_command"].startswith("claude")
    assert config["ask"]["answerer_command"].startswith("claude")


def test_config_text_documents_the_parakeet_alternative_as_a_comment():
    config = tomllib.loads(home.config_text())
    assert "parakeet" not in config["transcribe"]["transcriber_command"]
    assert "adapt-parakeet" in home.config_text(), "the alternative must be visible"


def test_the_shipped_remedy_table_reaches_every_tool_the_seams_name():
    config = tomllib.loads(home.config_text())
    table = config["setup"]["remedy"]
    heads = {"ffmpeg"}
    for section in ("ingest", "transcribe", "ask"):
        heads |= {
            shlex.split(value)[0]
            for key, value in config[section].items()
            if key.endswith("_command")
        }
    assert not heads - set(table), "a fresh install must always be told what to do next"
    assert table["parakeet-mlx"].startswith("uv tool install")


def test_toml_literal_keeps_double_quotes_untouched():
    value = 'yt-dlp -f "bv*[vcodec^=avc1]" -o "$DEST/video.%(ext)s"'
    assert tomllib.loads(f"x = {home._toml(value)}")["x"] == value


def test_toml_falls_back_to_a_basic_string_when_a_quote_is_in_the_way():
    value = "sh -c 'echo hi'"
    assert tomllib.loads(f"x = {home._toml(value)}")["x"] == value


def test_default_home_is_visible_and_belongs_to_the_user(monkeypatch):
    monkeypatch.delenv("TAPEDECK_HOME", raising=False)
    monkeypatch.setenv("HOME", "/tmp/someone")
    assert str(home.resolve()) == "/tmp/someone/Tapedeck"


def test_tapedeck_home_overrides_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "elsewhere"))
    assert home.resolve() == tmp_path / "elsewhere"


def test_scaffold_never_rewrites_what_is_already_there(tmp_path):
    home.scaffold(tmp_path)
    (tmp_path / home.CONFIG_NAME).write_text("mine\n")
    home.scaffold(tmp_path)
    assert (tmp_path / home.CONFIG_NAME).read_text() == "mine\n"
    assert (tmp_path / "library").is_dir() and (tmp_path / "archive").is_dir()


def test_the_brief_carries_the_grounding_rules():
    assert "not in the library" in home.BRIEF
    assert "cite" in home.BRIEF.lower()


# --- doctor -------------------------------------------------------------------


def test_head_is_the_first_shell_word():
    assert doctor.head('yt-dlp -f "bv*[height<=1080]"') == "yt-dlp"
    assert doctor.head("sh -c 'echo mine'") == "sh"
    assert doctor.head("parakeet-mlx x && tapedeck adapt-parakeet") == "parakeet-mlx"
    assert doctor.head("") == ""


def test_head_survives_a_template_the_shell_could_not_parse():
    assert doctor.head("yt-dlp -o 'unbalanced") == "yt-dlp"


def test_a_seam_that_resolves_passes_without_naming_a_path():
    row = doctor.seam_row({"ingest": {"fetcher_command": "sh -c :"}}, "ingest", "f", True, None)
    assert row["status"] == doctor.PASS
    assert row["missing"] is None
    assert "/" not in row["detail"], "the pass reason is the name, not where it lives"


def test_a_seam_that_cannot_resolve_carries_the_name_the_wizard_needs():
    settings = {"transcribe": {"transcriber_command": f"{MISSING} --model large"}}
    row = doctor.seam_row(settings, "transcribe", "transcriber_command", True, None)
    assert row["status"] == doctor.FAIL
    assert row["missing"] == MISSING and MISSING in row["detail"]


def test_an_optional_seam_never_reads_as_a_failure():
    row = doctor.seam_row({"ask": {"librarian_command": MISSING}}, "ask", "l", False, None)
    assert row["status"] == doctor.OPTIONAL
    assert doctor.failed([row]) == []
    assert "ask" in row["detail"] and "search" in row["detail"]


def test_public_rows_are_exactly_what_the_surface_promises():
    rows = doctor.public([doctor.row("x", doctor.PASS, "fine", missing="hidden")])
    assert rows == [{"check": "x", "status": doctor.PASS, "detail": "fine"}]


def test_the_report_puts_every_status_in_one_column():
    rows = [doctor.row("a.long.check", doctor.FAIL, "why"), doctor.row("b", doctor.PASS, "fine")]
    columns = {line.index(item["status"]) for item, line in zip(rows, doctor.report(rows).splitlines())}
    assert len(columns) == 1


def test_the_platform_check_only_objects_to_mlx_on_the_wrong_silicon():
    assert doctor.platform_row("whisper-cpp --model x")["status"] == doctor.PASS
    here = sys.platform == "darwin" and platform.machine() == "arm64"
    row = doctor.platform_row("mlx_whisper --model turbo")
    assert row["status"] == (doctor.PASS if here else doctor.FAIL)


# --- setup: the wizard --------------------------------------------------------


def write_config(tmp_path, body):
    (tmp_path / home.CONFIG_NAME).write_text(body)
    return tmp_path


def test_a_config_remedy_overrides_the_shipped_one_and_the_rest_survive(tmp_path):
    write_config(tmp_path, "[setup]\nremedy.ffmpeg = 'port install ffmpeg'\n")
    table = setup.remedies(tmp_path)
    assert table["ffmpeg"] == "port install ffmpeg", "the user's line wins"
    assert table["yt-dlp"] == home.DEFAULT_REMEDIES["yt-dlp"], "the rest are still known"


def test_a_home_with_no_setup_table_still_knows_the_shipped_remedies(tmp_path):
    assert setup.remedies(tmp_path) == home.DEFAULT_REMEDIES


def test_the_consented_commands_are_the_required_ones_in_report_order(tmp_path):
    rows = [
        doctor.row("ingest.fetcher_command", doctor.FAIL, "...", missing="yt-dlp"),
        doctor.row("ingest.lister_command", doctor.FAIL, "...", missing="yt-dlp"),
        doctor.row("ask.librarian_command", doctor.OPTIONAL, "...", missing="claude"),
        doctor.row("ffmpeg", doctor.FAIL, "...", missing="ffmpeg"),
        doctor.row("home", doctor.FAIL, "not writable"),
    ]
    assert setup.commands(rows, home.DEFAULT_REMEDIES) == [
        "brew install yt-dlp",
        "brew install ffmpeg",
    ], "one entry per remedy, in the printed order, and never an optional one"


def test_a_required_gap_with_nothing_to_install_says_so():
    row = doctor.row("home", doctor.FAIL, "not writable")
    assert setup.fix(row, home.DEFAULT_REMEDIES) == setup.NOT_AN_INSTALL


def test_a_missing_tool_the_table_never_heard_of_is_named_honestly():
    row = doctor.row("ingest.fetcher_command", doctor.FAIL, "...", missing=MISSING)
    fix = setup.fix(row, home.DEFAULT_REMEDIES)
    assert MISSING in fix and "no remedy" in fix


def test_homebrew_is_only_mentioned_when_a_brew_remedy_needs_it(monkeypatch, capsys):
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    assert setup.homebrew_gate(["brew install yt-dlp"]) is True
    out = capsys.readouterr().out
    assert "Homebrew" in out and "brew.sh" in out

    monkeypatch.setattr(setup.shutil, "which", lambda name: "/somewhere/" + name)
    assert setup.homebrew_gate(["brew install yt-dlp"]) is False
    assert setup.homebrew_gate(["uv tool install mlx-whisper"]) is False
    assert capsys.readouterr().out == "", "brew is here; saying so is noise"


def test_the_optional_block_lists_each_tool_once_and_never_as_a_gap(capsys):
    rows = [
        doctor.row("ask.librarian_command", doctor.OPTIONAL, "...", missing="claude"),
        doctor.row("ask.answerer_command", doctor.OPTIONAL, "...", missing="claude"),
    ]
    setup.optional(rows, home.DEFAULT_REMEDIES)
    out = capsys.readouterr().out
    assert out.count("claude ") + out.count("claude\n") >= 1
    assert out.count(home.DEFAULT_REMEDIES["claude"]) == 1
    assert "never installs them" in out


def test_the_model_note_names_a_size_only_where_tapedeck_knows_one(tmp_path, capsys):
    rows = [doctor.row("transcribe.transcriber_command", doctor.PASS, "parakeet-mlx on PATH")]
    write_config(tmp_path, "[transcribe]\ntranscriber_command = 'parakeet-mlx --json'\n")
    setup.model_note(rows, tmp_path)
    assert "~2.4GB" in capsys.readouterr().out

    write_config(tmp_path, "[transcribe]\ntranscriber_command = 'whisper-cpp'\n")
    setup.model_note(rows, tmp_path)
    note = capsys.readouterr().out
    assert "first transcription" in note and "~" not in note


def test_no_note_at_all_when_the_transcriber_is_not_installed(tmp_path, capsys):
    rows = [doctor.row("transcribe.transcriber_command", doctor.FAIL, "gone", missing="x")]
    setup.model_note(rows, tmp_path)
    assert capsys.readouterr().out == ""


def test_the_verdict_agrees_with_the_report(capsys):
    assert setup.verdict([doctor.row("home", doctor.PASS, "fine")], advise=True) == 0
    assert "ready" in capsys.readouterr().out.lower()
    broken = [doctor.row("ffmpeg", doctor.FAIL, "gone", missing="ffmpeg")]
    assert setup.verdict(broken, advise=True) == 1
    assert "--yes" in capsys.readouterr().out
    assert setup.verdict(broken, advise=False) == 1
    assert "--yes" not in capsys.readouterr().out, "past the offer once it has been taken"


def test_setup_without_yes_runs_nothing_and_exits_on_the_gaps(tmp_path, monkeypatch, capsys):
    def refuse(*args, **kwargs):  # nothing may reach a shell without --yes
        raise AssertionError("setup executed a command without consent")

    monkeypatch.setattr(setup.subprocess, "run", refuse)
    write_config(
        tmp_path,
        "[ingest]\n"
        f"fetcher_command = '{MISSING}'\n"
        "lister_command = 'sh -c :'\n"
        "[transcribe]\ntranscriber_command = 'sh -c :'\n"
        f"[setup]\nremedy.{MISSING} = 'install-it-somehow'\n",
    )
    assert setup.run(tmp_path, yes=False) == 1
    out = capsys.readouterr().out
    assert str(tmp_path) in out, "the resolved home is visible before anything else"
    assert "install-it-somehow" in out


# --- the surface --------------------------------------------------------------


def test_every_verb_on_the_surface_has_a_worked_example():
    _, verbs = build_parser()
    assert set(verbs) - set(teach.EXAMPLES) == set()


def test_setup_takes_yes_and_nothing_else():
    parser, _ = build_parser()
    assert parser.parse_args(["setup"]).yes is False
    assert parser.parse_args(["setup", "--yes"]).yes is True


def test_the_tour_is_one_screen_and_names_the_new_machine_verb():
    text = teach.tour()
    assert len(text.splitlines()) <= 45
    assert "tapedeck setup" in text
    assert "dev/storage/tapedeck" not in text


def test_an_unknown_help_topic_names_what_is_known():
    _, verbs = build_parser()
    with pytest.raises(Usage) as caught:
        teach.teach("bogus", verbs)
    assert "manual" in str(caught.value) and "setup" in str(caught.value)


def test_an_id_that_is_not_in_the_library_is_a_usage_error(tmp_path):
    with pytest.raises(Usage):
        views.known(tmp_path, "nosuchvid00")
