"""Ephemeral unit tests for the cli's pure parts.

The durable evaluations under system/evals/cli drive the executable; these poke
at the pieces that are awkward to reach from there — the TOML the scaffold
writes, the head-executable rule, the report's column, the tour's length.
"""

import json
import tomllib

import pytest

from cli import Usage, doctor, home, pipeline, teach, views
from cli.main import build_parser


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
    assert doctor.head('parakeet-mlx x && tapedeck adapt-parakeet') == "parakeet-mlx"
    assert doctor.head("") == ""


def test_head_survives_a_template_the_shell_could_not_parse():
    assert doctor.head('weird "unbalanced --flag') == "weird"


def test_a_required_seam_that_cannot_resolve_fails():
    row = doctor.seam_row({"ingest": {"fetcher_command": "no-such-tool-xyz"}},
                          "ingest", "fetcher_command", True, None)
    assert row["status"] == "fail"
    assert "no-such-tool-xyz" in row["detail"]


def test_an_ask_seam_is_optional_and_says_what_it_costs():
    row = doctor.seam_row({}, "ask", "librarian_command", False, None)
    assert row["status"] == "optional"
    assert "ask" in row["detail"] and "search" in row["detail"]


def test_a_resolvable_seam_passes_whatever_tool_it_names():
    row = doctor.seam_row({"ingest": {"fetcher_command": "sh -c :"}},
                          "ingest", "fetcher_command", True, None)
    assert row["status"] == "pass" and "sh" in row["detail"]


def test_platform_fails_mlx_off_apple_silicon(monkeypatch):
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
    row = doctor.platform_row("mlx_whisper --model whatever")
    assert row["status"] == "fail"
    assert "Apple Silicon" in row["detail"]
    assert "transcriber_command" in row["detail"]


def test_platform_has_nothing_to_say_about_a_portable_transcriber(monkeypatch):
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    assert doctor.platform_row("sh -c 'whisper-cpp'")["status"] == "pass"


def test_diagnose_emits_every_check_in_the_pinned_order(tmp_path):
    home.scaffold(tmp_path)
    rows = doctor.diagnose(tmp_path)
    assert [row["check"] for row in rows] == [
        "ingest.fetcher_command", "ingest.lister_command",
        "transcribe.transcriber_command", "ask.librarian_command",
        "ask.answerer_command", "ffmpeg", "home", "fts5", "platform",
    ]
    for row in rows:
        assert set(row) == {"check", "status", "detail"}
        assert row["detail"].strip()


def test_an_unreadable_config_is_a_diagnosis_not_a_crash(tmp_path):
    (tmp_path / home.CONFIG_NAME).write_text("this is not [ toml\n")
    rows = {row["check"]: row for row in doctor.diagnose(tmp_path)}
    assert rows["ingest.fetcher_command"]["status"] == "fail"
    assert rows["ask.answerer_command"]["status"] == "optional"


def test_the_report_starts_every_status_at_one_column():
    rows = [
        doctor.row("ingest.fetcher_command", "pass", "yt-dlp at /usr/bin/yt-dlp"),
        doctor.row("transcribe.transcriber_command", "fail", "nope: not on PATH"),
        doctor.row("home", "optional", "somewhere"),
    ]
    columns = {line.index(row["status"]) for line, row in
               zip(doctor.report(rows).splitlines(), rows)}
    assert len(columns) == 1


def test_fts5_is_reported_on_this_python():
    assert doctor.fts5_row()["check"] == "fts5"


# --- teach --------------------------------------------------------------------


def test_the_tour_is_one_screen_and_names_the_everyday_verbs():
    text = teach.tour()
    assert len(text.splitlines()) <= 45
    for verb in ("add", "search", "ask", "list", "show", "retranscribe"):
        assert verb in text
    assert "~/Tapedeck" in text
    assert "dev/storage/tapedeck" not in text
    assert "\x1b" not in text


def test_an_unknown_topic_names_what_it_knows():
    _, verbs = build_parser()
    with pytest.raises(Usage) as caught:
        teach.teach("bogus", verbs)
    assert "manual" in str(caught.value)


def test_every_verb_has_a_worked_example():
    _, verbs = build_parser()
    assert set(teach.EXAMPLES) == set(verbs)


def test_the_manual_is_found_and_read():
    assert teach.manual_text().startswith("# The Tapedeck Manual")


# --- pipeline -----------------------------------------------------------------


def library_entry(home_dir, video_id, *, media=True, transcript="fixture/whisper-0", page=True):
    entry = home_dir / "library" / video_id
    entry.mkdir(parents=True)
    if media:
        (entry / "video.mp4").write_bytes(b"\x00")
    (entry / "meta.json").write_text(json.dumps({"id": video_id, "title": "T",
                                                 "channel": "C", "upload_date": "2026-01-01",
                                                 "duration_s": 60, "url": "u"}))
    if transcript:
        (entry / "transcript.json").write_text(json.dumps({"model": transcript}))
    if page:
        (home_dir / "archive").mkdir(exist_ok=True)
        (home_dir / "archive" / f"{video_id}.md").write_text("page\n")
    return entry


def test_complete_needs_every_link(tmp_path):
    home.scaffold(tmp_path)
    library_entry(tmp_path, "aaaaaaaaaaa")
    assert pipeline.complete(tmp_path, "aaaaaaaaaaa")
    (tmp_path / "archive" / "aaaaaaaaaaa.md").unlink()
    assert not pipeline.complete(tmp_path, "aaaaaaaaaaa")


def test_a_part_file_is_not_a_video(tmp_path):
    home.scaffold(tmp_path)
    entry = library_entry(tmp_path, "bbbbbbbbbbb")
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    assert not pipeline.complete(tmp_path, "bbbbbbbbbbb"), "ingest's rule, not ours"


def test_superseded_selects_only_what_it_could_redo(tmp_path, capsys):
    home.scaffold(tmp_path)
    library_entry(tmp_path, "aaaaaaaaaaa", transcript="old")
    library_entry(tmp_path, "bbbbbbbbbbb", transcript="new")
    library_entry(tmp_path, "ccccccccccc", transcript="old", media=False)
    (tmp_path / "library" / "reading-notes").mkdir()

    assert pipeline.superseded(tmp_path, "new") == ["aaaaaaaaaaa"]
    noted = capsys.readouterr().err
    assert "ccccccccccc" in noted and "reading-notes" in noted


def test_a_missing_transcript_is_superseded(tmp_path):
    home.scaffold(tmp_path)
    library_entry(tmp_path, "aaaaaaaaaaa", transcript=None)
    assert pipeline.superseded(tmp_path, "new") == ["aaaaaaaaaaa"]


# --- views --------------------------------------------------------------------


def test_entries_uses_ingests_id_grammar(tmp_path):
    home.scaffold(tmp_path)
    library_entry(tmp_path, "aaaaaaaaaaa")
    (tmp_path / "library" / "reading-notes").mkdir()
    assert [p.name for p in views.entries(tmp_path)] == ["aaaaaaaaaaa"]


def test_show_reports_no_media_rather_than_a_part_file(tmp_path, capsys):
    home.scaffold(tmp_path)
    entry = library_entry(tmp_path, "aaaaaaaaaaa")
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")

    assert views.show(tmp_path, "aaaaaaaaaaa", True) == 0
    assert json.loads(capsys.readouterr().out)["media"] is None
    assert views.show(tmp_path, "aaaaaaaaaaa", False) == 0
    assert "video.part" not in capsys.readouterr().out


def test_an_unknown_id_is_a_usage_error(tmp_path):
    home.scaffold(tmp_path)
    with pytest.raises(Usage) as caught:
        views.show(tmp_path, "nosuchvid00", False)
    assert "nosuchvid00" in str(caught.value)


def test_list_is_newest_first(tmp_path, capsys):
    home.scaffold(tmp_path)
    library_entry(tmp_path, "aaaaaaaaaaa")
    entry = library_entry(tmp_path, "bbbbbbbbbbb")
    meta = json.loads((entry / "meta.json").read_text())
    meta["upload_date"] = "2026-06-06"
    (entry / "meta.json").write_text(json.dumps(meta))

    views.listing(tmp_path, True)
    assert [row["id"] for row in json.loads(capsys.readouterr().out)] == [
        "bbbbbbbbbbb", "aaaaaaaaaaa",
    ]


# --- the surface --------------------------------------------------------------


def test_the_parser_exposes_exactly_the_contract_surface():
    _, verbs = build_parser()
    assert set(verbs) == {
        "add", "search", "ask", "list", "show", "reindex", "rm",
        "retranscribe", "adapt-parakeet", "doctor", "help",
    }
