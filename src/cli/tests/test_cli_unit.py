"""Ephemeral unit tests for the cli component (disposable, not the contract).

The durable evaluations in system/evals/cli/ drive the installed executable and
are the acceptance criteria. These sit closer in: the pure decisions — what the
scaffolded config says, what counts as complete, which topics `help` knows —
where a subprocess round trip would only make a failure harder to read.
"""

from __future__ import annotations

import io
import json
import tomllib

import pytest

from cli import Failure, home, library, main, teach, views


@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv(home.HOME_VAR, str(tmp_path / "deck"))
    return home.prepare()


# --- the home ----------------------------------------------------------------


def test_default_home_is_visible_and_in_the_users_home(tmp_path, monkeypatch):
    monkeypatch.delenv(home.HOME_VAR, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert home.resolve() == tmp_path / "Tapedeck"


def test_tapedeck_home_is_taken_verbatim(tmp_path, monkeypatch):
    monkeypatch.setenv(home.HOME_VAR, str(tmp_path / "elsewhere"))
    assert home.resolve() == tmp_path / "elsewhere"


def test_prepare_scaffolds_once_and_never_overwrites(deck):
    (deck / home.CONFIG_NAME).write_text("# mine now\n")
    (deck / home.BRIEF_NAME).write_text("# my brief\n")
    home.prepare()
    assert (deck / home.CONFIG_NAME).read_text() == "# mine now\n"
    assert (deck / home.BRIEF_NAME).read_text() == "# my brief\n"


def test_the_scaffolded_config_is_valid_toml_with_every_seam(deck):
    config = tomllib.loads((deck / home.CONFIG_NAME).read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "--flat-playlist" in config["ingest"]["lister_command"]
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert config["ask"]["librarian_command"].startswith("claude")
    assert config["ask"]["answerer_command"].startswith("claude")


def test_the_parakeet_alternative_is_documented_but_not_active(deck):
    text = (deck / home.CONFIG_NAME).read_text()
    assert "# transcriber_command = " in text and "adapt-parakeet" in text
    config = tomllib.loads(text)
    assert "parakeet" not in config["transcribe"]["transcriber_command"]


def test_a_command_with_a_quote_still_round_trips():
    tricky = "say 'hi' && grep \"x\""
    assert tomllib.loads(f"c = {home._toml(tricky)}")["c"] == tricky


# --- reading the library -----------------------------------------------------


VIDEO = "dQw4w9WgXcQ"


def stock(deck, video_id=VIDEO, media=True, transcript=True, page=True, model="m/1"):
    entry = deck / home.LIBRARY / video_id
    entry.mkdir(parents=True, exist_ok=True)
    if media:
        (entry / "video.mp4").write_bytes(b"\x00video")
    (entry / "meta.json").write_text(
        json.dumps(
            {
                "id": video_id,
                "title": "A Video",
                "channel": "A Channel",
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
        (deck / home.ARCHIVE / f"{video_id}.md").write_text("# A Video\n")
    return entry


def test_complete_means_every_link_of_the_chain(deck):
    stock(deck)
    assert library.complete(deck, VIDEO)


@pytest.mark.parametrize("missing", ["media", "transcript", "page"])
def test_a_missing_link_is_not_complete(deck, missing):
    stock(deck, **{missing: False})
    assert not library.complete(deck, VIDEO)


def test_a_partial_download_is_not_media(deck):
    entry = stock(deck)
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    assert library.media(deck, VIDEO) is None
    assert not library.complete(deck, VIDEO)


def test_ids_are_ingests_grammar_and_strays_are_still_named(deck):
    stock(deck)
    (deck / home.LIBRARY / "reading-notes").mkdir()
    assert library.ids(deck) == [VIDEO]
    assert "reading-notes" in library.names(deck)


def test_a_missing_or_unlabelled_transcript_has_no_label(deck):
    stock(deck, transcript=False)
    assert library.label(deck, VIDEO) is None
    stock(deck, model="fixture/2")
    assert library.label(deck, VIDEO) == "fixture/2"


def test_known_covers_a_page_left_behind_by_an_entry(deck):
    stock(deck)
    assert library.known(deck, VIDEO)
    assert not library.known(deck, "nosuchvid00")


# --- views -------------------------------------------------------------------


def test_show_json_reports_absent_media_as_null(deck, capsys):
    entry = stock(deck)
    (entry / "video.mp4").unlink()
    assert views.show(deck, VIDEO, as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["media"] is None


def test_show_human_never_names_a_file_that_is_not_the_video(deck, capsys):
    entry = stock(deck)
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    views.show(deck, VIDEO, as_json=False)
    assert "video.part" not in capsys.readouterr().out


def test_show_refuses_an_id_that_is_not_here(deck):
    with pytest.raises(Failure) as raised:
        views.show(deck, "nosuchvid00", as_json=False)
    assert raised.value.code == 2


def test_listing_is_newest_first(deck, capsys):
    stock(deck)
    older = stock(deck, video_id="plainvide00")
    document = json.loads((older / "meta.json").read_text())
    document["upload_date"] = "2020-01-01"
    (older / "meta.json").write_text(json.dumps(document))
    views.listing(deck, as_json=True)
    assert [row["id"] for row in json.loads(capsys.readouterr().out)] == [
        VIDEO,
        "plainvide00",
    ]


# --- the surface and the teaching -------------------------------------------


SURFACE = (
    "add", "search", "ask", "list", "show", "reindex", "rm",
    "retranscribe", "adapt-parakeet", "help",
)


def test_the_parser_carries_exactly_the_contracted_verbs():
    _, verbs = main.build_parser()
    assert sorted(verbs) == sorted(SURFACE)


def test_help_lists_every_verb():
    parser, _ = main.build_parser()
    text = parser.format_help()
    for verb in SURFACE:
        assert verb in text


def test_a_question_that_starts_with_a_dash_still_reaches_the_component():
    assert main._passthrough(["--fast"], "-k is not a flag here") == [
        "--fast",
        "--",
        "-k is not a flag here",
    ]


def test_the_tour_is_one_screen_and_teaches_by_example():
    out = io.StringIO()
    teach.tour(out)
    text = out.getvalue()
    assert len(text.splitlines()) <= 45
    assert "tapedeck add" in text
    assert "\x1b" not in text  # a StringIO is nobody's terminal


def test_every_verb_has_a_worked_example():
    _, verbs = main.build_parser()
    for verb in verbs:
        assert teach.EXAMPLES.get(verb), f"no example for {verb}"


def test_an_unknown_topic_names_what_help_knows():
    _, verbs = main.build_parser()
    with pytest.raises(Failure) as raised:
        teach.teach(verbs, "bogus", io.StringIO())
    assert raised.value.code == 2
    assert "manual" in str(raised.value)


def test_manual_piped_is_the_file_verbatim():
    out = io.StringIO()
    teach.teach({}, "manual", out)
    assert out.getvalue() == teach.manual_path().read_text(encoding="utf-8")


def test_no_color_silences_the_terminal_niceties(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert teach.decorated(Terminal())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not teach.decorated(Terminal())


def test_version_reads_the_installed_metadata(capsys):
    assert main.show_version() == 0
    printed = capsys.readouterr().out.split()
    assert printed[0] == "tapedeck" and printed[1][0].isdigit()
