"""Ephemeral unit tests for ask — the seams and readings the durable evals bracket.

These are disposable: they test the current implementation's units, where the suite
under system/evals/ask/ tests the boundary that outlives it. Run:

    uv run --with pytest pytest src/ask/tests -q
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from ask import citations, retrieve, seams
from ask.__main__ import Failure, main
from ask.citations import Citation, deep_links, hms, invented, prompt, sources_block, unverified
from ask.library import Library
from ask.retrieve import IndexUnreadable, Source, connect, excerpt, match_expression, terms
from index.pages import Page, Section
from index.store import DB_NAME, SCHEMA_VERSION, TOKENIZE, build

CHAPTERED = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video: Building Things",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}


def watch(video_id="dQw4w9WgXcQ", t=None):
    stamp = "" if t is None else f"&t={t}"
    return f"https://www.youtube.com/watch?v={video_id}{stamp}"


class FakeLibrary:
    """Just the two questions citations asks of a library."""

    def __init__(self, videos):
        self.videos = videos

    def holds(self, video_id):
        return video_id in self.videos

    def duration(self, video_id):
        return self.videos.get(video_id)


ONE_VIDEO = {"dQw4w9WgXcQ": 720}


# --- library: presence, duration, and what "unknown" means -------------------


def stock(home, meta=CHAPTERED):
    entry = home / "library" / meta["id"]
    entry.mkdir(parents=True)
    (entry / "meta.json").write_text(json.dumps(meta))
    return entry


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    return h


def test_holds_is_one_path_question(home):
    stock(home)
    library = Library(home)
    assert library.holds("dQw4w9WgXcQ")
    assert not library.holds("nosuchvid00")
    assert library.duration("dQw4w9WgXcQ") == 720


def test_a_malformed_id_is_never_held(home):
    stock(home)
    assert not Library(home).holds("../../etc")
    assert not Library(home).holds("dQw4w9WgXcQ.")  # a full stop is not part of an id


def test_zero_duration_means_unknown_not_zero_seconds(home):
    stock(home, {**CHAPTERED, "id": "unknownlen0", "duration_s": 0})
    library = Library(home)
    assert library.holds("unknownlen0")
    assert library.duration("unknownlen0") is None


def test_missing_or_unreadable_metadata_still_counts_as_present(home):
    (home / "library" / "nometaonevi").mkdir(parents=True)
    entry = stock(home, {**CHAPTERED, "id": "brokenmeta0"})
    (entry / "meta.json").write_text("{not json")
    library = Library(home)
    for video_id in ("nometaonevi", "brokenmeta0"):
        assert library.holds(video_id)
        assert library.duration(video_id) is None


def test_facts_are_read_once_per_id(home):
    stock(home)
    library = Library(home)
    assert library.duration("dQw4w9WgXcQ") == 720
    (home / "library" / "dQw4w9WgXcQ" / "meta.json").unlink()
    assert library.duration("dQw4w9WgXcQ") == 720  # remembered, not re-read


def test_stocked_sees_a_video_and_an_empty_library(home):
    assert not Library(home).stocked()
    stock(home)
    assert Library(home).stocked()


def test_a_dotted_directory_is_not_a_video(home):
    (home / "library" / ".tmp-fetch").mkdir()
    assert not Library(home).stocked()


# --- citations: where a URL ends --------------------------------------------


def test_a_bare_link_ending_a_sentence_keeps_its_id():
    (cite,) = deep_links(f"Covered at {watch()}.")
    assert cite.video_id == "dQw4w9WgXcQ"
    assert cite.url == watch()
    assert cite.seconds is None and not cite.stated


@pytest.mark.parametrize("punctuation", [".", ",", ";", ":", "!", "?", '"', "'", "…"])
def test_prose_punctuation_never_lands_in_the_offset(punctuation):
    (cite,) = deep_links(f"See {watch(t='95s')}{punctuation} and on we go")
    assert cite.video_id == "dQw4w9WgXcQ"
    assert cite.seconds == 95
    assert cite.stated


def test_a_markdown_link_stops_at_its_closing_paren():
    (cite,) = deep_links(f"Covered [here]({watch(t='95s')}).")
    assert cite.url == watch(t="95s")
    assert cite.seconds == 95


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [("95", 95), ("95s", 95), ("1h2m3s", 3723), ("2m", 120), ("1m30s", 90)],
)
def test_youtube_offset_spellings(raw, seconds):
    (cite,) = deep_links(f"See {watch(t=raw)}")
    assert cite.seconds == seconds


def test_a_short_link_carries_its_id_in_the_path():
    (cite,) = deep_links("See https://youtu.be/dQw4w9WgXcQ?t=95s.")
    assert cite.video_id == "dQw4w9WgXcQ"
    assert cite.seconds == 95


def test_several_citations_in_one_answer():
    text = f"One {watch(t='95s')}, two [x]({watch('plainvide00', '10s')})."
    assert [c.video_id for c in deep_links(text)] == ["dQw4w9WgXcQ", "plainvide00"]


def test_prose_that_cites_nothing():
    assert deep_links("A confident answer with no citations at all.") == []
    assert deep_links("See https://example.com/watch?v=dQw4w9WgXcQ") == []


# --- citations: what the library will vouch for ------------------------------


def test_a_real_moment_in_a_real_video_stands():
    assert unverified(deep_links(f"[x]({watch(t='95s')})"), FakeLibrary(ONE_VIDEO)) == []


def test_the_end_of_a_video_is_inside_it():
    assert unverified(deep_links(f"[x]({watch(t='720s')})"), FakeLibrary(ONE_VIDEO)) == []


def test_a_video_the_library_does_not_hold_is_a_fabrication():
    (problem,) = unverified(deep_links(f"[x]({watch('nosuchvid00')})"), FakeLibrary(ONE_VIDEO))
    assert "nosuchvid00" in problem


def test_a_moment_past_the_end_is_a_fabrication():
    (problem,) = unverified(deep_links(f"[x]({watch(t='9999s')})"), FakeLibrary(ONE_VIDEO))
    assert "9999" in problem and "2:46:39" in problem


def test_a_moment_past_the_end_is_caught_through_trailing_punctuation():
    """The bug this pins: `t=9999s.` must not parse to nothing and be waived."""
    (problem,) = unverified(deep_links(f"Settled at {watch(t='9999s')}."), FakeLibrary(ONE_VIDEO))
    assert "9999" in problem


def test_an_unreadable_offset_fails_rather_than_passes():
    """A `t=` the parser gives up on claims a moment nobody can check."""
    (cite,) = deep_links(f"[x]({watch(t='soon')})")
    assert cite == Citation(watch(t="soon"), "dQw4w9WgXcQ", None, stated=True)
    (problem,) = unverified([cite], FakeLibrary(ONE_VIDEO))
    assert "cannot be read" in problem


def test_an_unknown_duration_bounds_nothing():
    library = FakeLibrary({"unknownlen0": None})
    assert unverified(deep_links(f"[x]({watch('unknownlen0', '9999s')})"), library) == []


def test_an_unknown_duration_does_not_excuse_an_absent_video():
    library = FakeLibrary({"unknownlen0": None})
    assert unverified(deep_links(f"[x]({watch('nosuchvid00', '9s')})"), library)


def test_a_scope_rejects_another_video_the_library_really_has():
    library = FakeLibrary({"dQw4w9WgXcQ": 720, "plainvide00": 720})
    links = deep_links(f"[x]({watch('plainvide00', '10s')})")
    (problem,) = unverified(links, library, scope="dQw4w9WgXcQ")
    assert "outside the --video" in problem
    assert unverified(deep_links(f"[x]({watch(t='10s')})"), library, scope="dQw4w9WgXcQ") == []


# --- citations: the fast-mode contract ---------------------------------------


def source(number=1, section="The Core Idea"):
    return Source(
        video_id="dQw4w9WgXcQ",
        title="Test Video: Building Things",
        channel="Fixture Channel",
        section=section,
        start_s=95 * number,
        text="The core idea is regeneration over maintenance.",
    )


def test_the_prompt_carries_the_rules_the_sources_and_the_question():
    text = prompt("what is the core idea", [source()])
    assert "what is the core idea" in text
    assert "The core idea is regeneration over maintenance." in text
    assert "not in the library" in text
    assert "[1]" in text
    assert "The Core Idea" in text


def test_sources_are_numbered_as_retrieved_cited_or_not():
    block = sources_block([source(1), source(2)])
    assert "[1] Test Video: Building Things — Fixture Channel @ 0:01:35" in block
    assert "[2] Test Video: Building Things — Fixture Channel @ 0:03:10" in block
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=190s" in block


def test_a_marker_no_source_carries_is_invented():
    assert invented("Something confident [9].", 2) == [9]
    assert invented("As shown [1] and [2].", 2) == []
    assert invented("Nothing cited at all.", 2) == []


def test_hms_and_the_scope_note():
    assert (hms(0), hms(95), hms(3723)) == ("0:00:00", "0:01:35", "1:02:03")
    assert citations.ask_for("q", None) == "q\n"
    assert "dQw4w9WgXcQ" in citations.ask_for("q", "dQw4w9WgXcQ")


# --- retrieval: what a question asks for -------------------------------------


def test_question_grammar_is_dropped_and_the_rest_ored():
    assert terms("what is the core idea") == ["core", "idea"]
    assert match_expression("what is the core idea") == '"core" OR "idea"'


def test_a_question_of_pure_grammar_keeps_its_words():
    assert terms("what is it") == ["what", "is", "it"]


def test_a_quoted_group_survives_and_punctuation_cannot_be_syntax():
    assert terms('why "core idea" C++ ***') == ["core idea", "C++"]
    assert match_expression('say "a b"') == '"say" OR "a b"'
    assert match_expression("???") == ""


def test_a_long_section_is_cut_at_a_word_boundary():
    text = "word " * 500
    cut = excerpt(text)
    assert len(cut) <= retrieve.EXCERPT_CHARS + 2 and cut.endswith("…")
    assert excerpt("  short  ") == "short"


# --- retrieval: the shape gate (SPEC-ask-004) --------------------------------


def page(video_id="dQw4w9WgXcQ"):
    return Page(
        video_id=video_id,
        title="Test Video: Building Things",
        channel="Fixture Channel",
        upload_date="2026-01-15",
        url=watch(video_id),
        duration_s=720,
        sections=(Section(95, "The Core Idea", "The core idea is regeneration."),),
    )


def indexed(home):
    home.mkdir(parents=True, exist_ok=True)
    build(home, [page()])
    return home / DB_NAME


def test_an_index_of_this_shape_answers(home):
    indexed(home)
    (found,) = retrieve.top_k(home, "what is the core idea", 8)
    assert found.video_id == "dQw4w9WgXcQ"
    assert found.channel == "Fixture Channel"
    assert found.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"


def test_no_index_at_all_names_the_reindex_hint(home):
    with pytest.raises(IndexUnreadable, match="reindex"):
        connect(home)


def test_another_schema_version_is_refused(home):
    path = indexed(home)
    con = sqlite3.connect(path)
    with con:
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    con.close()
    with pytest.raises(IndexUnreadable, match="reindex"):
        connect(home)


def test_another_tokenizer_under_the_current_version_is_refused(home):
    path = indexed(home)
    con = sqlite3.connect(path)
    with con:
        con.executescript("DROP TABLE chunks;")
        con.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5(video_id UNINDEXED, "
            "start_s UNINDEXED, section, text, tokenize = 'unicode61')"
        )
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.close()
    assert TOKENIZE not in "unicode61"
    with pytest.raises(IndexUnreadable, match="reindex"):
        connect(home)


def test_a_file_that_is_no_database_is_refused(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / DB_NAME).write_text("not a database")
    with pytest.raises(IndexUnreadable, match="reindex"):
        connect(home)


def test_the_connection_cannot_write(home):
    indexed(home)
    db = connect(home)
    with pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM videos")
    db.close()


def test_a_scope_narrows_the_retrieval_itself(home):
    home.mkdir(parents=True, exist_ok=True)
    build(home, [page(), page("plainvide00")])
    assert len(retrieve.top_k(home, "core idea", 8)) == 2
    scoped = retrieve.top_k(home, "core idea", 8, "plainvide00")
    assert [s.video_id for s in scoped] == ["plainvide00"]


# --- the boundary: modes, order, exit codes ----------------------------------


def seam(home, key, body):
    script = home / f"{key}.sh"
    script.write_text(body)
    (home / "config.toml").write_text(f'[ask]\n{key} = "sh {script}"\n')
    (home / "CLAUDE.md").write_text("# brief\n")


def run(home, monkeypatch, *argv):
    monkeypatch.setenv("TAPEDECK_HOME", str(home))
    return main(["run", *argv])


CITES = "#!/bin/sh\ncat > /dev/null\nprintf 'See [x](%s).\\n' 'URL'\n"


def librarian_saying(url):
    return CITES.replace("URL", url)


def test_librarian_mode_prints_a_verified_answer(home, monkeypatch, capsys):
    stock(home)
    seam(home, "librarian_command", librarian_saying(watch(t="95s")))
    assert run(home, monkeypatch, "what is this about") == 0
    assert "dQw4w9WgXcQ&t=95s" in capsys.readouterr().out


def test_librarian_mode_refuses_a_fabrication(home, monkeypatch):
    stock(home)
    seam(home, "librarian_command", librarian_saying(watch("nosuchvid00", "9s")))
    assert run(home, monkeypatch, "what is this about") == 1


def test_an_empty_library_never_reaches_the_librarian(home, monkeypatch):
    seam(home, "librarian_command", "#!/bin/sh\ntouch \"$TAPEDECK_HOME/ran\"\n")
    assert run(home, monkeypatch, "anything") == 1
    assert not (home / "ran").exists()


def test_a_missing_brief_is_a_config_error(home, monkeypatch):
    stock(home)
    seam(home, "librarian_command", librarian_saying(watch()))
    (home / "CLAUDE.md").unlink()
    assert run(home, monkeypatch, "anything") == 2


def test_an_unknown_scope_is_settled_before_anything_runs(home, monkeypatch):
    stock(home)
    seam(home, "librarian_command", "#!/bin/sh\ntouch \"$TAPEDECK_HOME/ran\"\n")
    assert run(home, monkeypatch, "anything", "--video", "nosuchvid00") == 2
    assert not (home / "ran").exists()


def test_a_bad_k_is_a_usage_error(home, monkeypatch):
    stock(home)
    assert run(home, monkeypatch, "anything", "-k", "0", "--fast") == 2


def test_fast_mode_appends_the_sources_it_retrieved(home, monkeypatch, capsys):
    indexed(home)
    seam(home, "answerer_command", "#!/bin/sh\ncat > \"$TAPEDECK_HOME/seen\"\nprintf 'Yes [1].\\n'\n")
    assert run(home, monkeypatch, "what is the core idea", "--fast") == 0
    out = capsys.readouterr().out
    assert "Yes [1]." in out and "Sources:" in out and "&t=95s" in out
    assert "what is the core idea" in (home / "seen").read_text()


def test_fast_mode_refuses_a_stale_index_without_invoking_the_answerer(home, monkeypatch):
    path = indexed(home)
    con = sqlite3.connect(path)
    with con:
        con.execute("PRAGMA user_version = 1")
    con.close()
    seam(home, "answerer_command", "#!/bin/sh\ntouch \"$TAPEDECK_HOME/ran\"\n")
    assert run(home, monkeypatch, "what is the core idea", "--fast") == 1
    assert not (home / "ran").exists()


def test_fast_mode_refuses_an_invented_marker(home, monkeypatch):
    indexed(home)
    seam(home, "answerer_command", "#!/bin/sh\ncat > /dev/null\nprintf 'Sure [9].\\n'\n")
    assert run(home, monkeypatch, "what is the core idea", "--fast") == 1


def test_an_answerer_that_fails_or_says_nothing_is_a_clean_error(home, monkeypatch):
    indexed(home)
    seam(home, "answerer_command", "#!/bin/sh\ncat > /dev/null\nexit 1\n")
    assert run(home, monkeypatch, "what is the core idea", "--fast") == 1
    seam(home, "answerer_command", "#!/bin/sh\ncat > /dev/null\n")
    assert run(home, monkeypatch, "what is the core idea", "--fast") == 1


def test_the_cli_verb_name_answers_too(home, monkeypatch):
    """`answer` is what src/cli/components.py calls; `run` is what the evals drive."""
    stock(home)
    seam(home, "librarian_command", librarian_saying(watch(t="95s")))
    monkeypatch.setenv("TAPEDECK_HOME", str(home))
    assert main(["answer", "what is this about"]) == 0


def test_seams_report_a_missing_command_as_a_config_error(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text("# no ask section\n")
    with pytest.raises(seams.ConfigError, match="librarian"):
        seams.command(home, seams.LIBRARIAN_KEY, "librarian")
    (home / "config.toml").write_text("[ask]\nlibrarian_command = '   '\n")
    with pytest.raises(seams.ConfigError):
        seams.command(home, seams.LIBRARIAN_KEY, "librarian")


def test_the_librarian_runs_in_the_library_home(home):
    home.mkdir(parents=True, exist_ok=True)
    assert seams.run("pwd", home, "", "librarian", cwd=home) == str(home)


def test_failure_carries_its_exit_code():
    assert Failure("nope", code=2).code == 2 and Failure("nope").code == 1
