"""Ephemeral unit tests for ask — the durable evals are system/evals/ask/.

These go under the surface the evals drive: query construction, the prompt text,
the citation gate, and the seam's failure modes. Run: uv run pytest src/ask -q
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ask import answerer, citations, retrieve  # noqa: E402
from ask.__main__ import main  # noqa: E402

SCHEMA = """
CREATE TABLE videos (
    video_id TEXT PRIMARY KEY, title TEXT, channel TEXT,
    upload_date TEXT, url TEXT, duration_s INTEGER
);
CREATE VIRTUAL TABLE chunks USING fts5(
    video_id UNINDEXED, start_s UNINDEXED, section, text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

CHUNKS = [
    ("dQw4w9WgXcQ", 0, "Intro", "Welcome to the fixture show."),
    ("dQw4w9WgXcQ", 95, "The Core Idea", "The core idea is regeneration over maintenance."),
    ("dQw4w9WgXcQ", 610, "Wrap Up", "Thanks for watching, goodbye."),
    ("plainvide00", 0, "Part 1", "Block one content about sourdough starters."),
    ("plainvide00", 300, "Part 2", "Block two content about proofing times."),
]
VIDEOS = [
    ("dQw4w9WgXcQ", "Test Video: Building Things", "Fixture Channel"),
    ("plainvide00", "Sourdough Basics", "Bread Channel"),
]


@pytest.fixture
def home(tmp_path):
    """A home with an index in exactly the shape `index reindex` leaves behind."""
    h = tmp_path / "home"
    h.mkdir()
    db = sqlite3.connect(h / "tapedeck.db")
    with db:
        db.executescript(SCHEMA)
        db.execute("PRAGMA user_version = 1")
        db.executemany(
            "INSERT INTO videos (video_id, title, channel) VALUES (?, ?, ?)", VIDEOS
        )
        db.executemany(
            "INSERT INTO chunks (video_id, start_s, section, text) VALUES (?, ?, ?, ?)", CHUNKS
        )
    db.close()
    return h


def answerer_script(home, body):
    script = home / "answer.sh"
    script.write_text(body)
    (home / "config.toml").write_text(f'[ask]\nanswerer_command = "sh {script}"\n')


def source(**over):
    fields = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video: Building Things",
        "channel": "Fixture Channel",
        "section": "The Core Idea",
        "start_s": 95,
        "text": "The core idea is regeneration over maintenance.",
    }
    return retrieve.Source(**{**fields, **over})


# --- query construction ------------------------------------------------------


def test_question_grammar_is_dropped_from_the_query():
    assert retrieve.terms("what is the core idea") == ["core", "idea"]


def test_punctuation_never_becomes_query_syntax():
    assert retrieve.match_expression("why C++? (really)") == '"C++?" OR "(really)"'


def test_quoted_groups_survive_even_when_they_are_grammar():
    assert retrieve.terms('what does "the way" mean') == ['the way', "mean"]


def test_a_question_of_pure_grammar_still_searches_for_something():
    assert retrieve.terms("what is it about") == ["what", "is", "it", "about"]


def test_a_wordless_question_matches_nothing(home):
    assert retrieve.match_expression("?! ...") == ""
    assert retrieve.top_k(home, "?! ...", 8) == []


def test_a_term_fts5_would_tokenize_to_nothing_is_dropped(home):
    # "___" is \w but not a word: fts5 refuses the empty phrase it becomes.
    assert retrieve.match_expression("___ ---") == ""
    assert retrieve.top_k(home, "___ core", 8)[0].start_s == 95


def test_terms_are_ored_so_partial_overlap_still_retrieves():
    assert retrieve.match_expression("core idea") == '"core" OR "idea"'


# --- retrieval ---------------------------------------------------------------


def test_top_k_ranks_the_answering_chunk_first(home):
    hits = retrieve.top_k(home, "what is the core idea", 3)
    assert hits[0].video_id == "dQw4w9WgXcQ"
    assert hits[0].start_s == 95
    assert hits[0].text == "The core idea is regeneration over maintenance."
    assert hits[0].title == "Test Video: Building Things"
    assert hits[0].channel == "Fixture Channel"


def test_retrieval_carries_the_contract_deep_link(home):
    hit = retrieve.top_k(home, "core idea", 1)[0]
    assert hit.timestamp == "0:01:35"
    assert hit.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"


def test_or_semantics_find_chunks_no_single_and_query_would(home):
    # No chunk holds all of content+sourdough+proofing; two hold two of them.
    hits = retrieve.top_k(home, "content about sourdough proofing", 8)
    assert {hit.start_s for hit in hits} == {0, 300}
    assert all(hit.video_id == "plainvide00" for hit in hits)


def test_k_bounds_the_result_count(home):
    assert len(retrieve.top_k(home, "content about sourdough proofing", 1)) == 1


def test_nothing_in_the_library_is_an_empty_list_not_an_error(home):
    assert retrieve.top_k(home, "xylophone quantum blockchain", 8) == []


def test_a_missing_index_says_how_to_get_one(tmp_path):
    with pytest.raises(retrieve.IndexUnreadable, match="reindex"):
        retrieve.top_k(tmp_path, "core idea", 8)


def test_an_index_of_another_shape_is_reported_not_guessed_at(tmp_path):
    (tmp_path / "tapedeck.db").write_bytes(b"not a database at all")
    with pytest.raises(retrieve.IndexUnreadable):
        retrieve.top_k(tmp_path, "core idea", 8)


def test_retrieval_never_writes_to_the_index(home):
    before = (home / "tapedeck.db").read_bytes()
    retrieve.top_k(home, "core idea", 8)
    assert (home / "tapedeck.db").read_bytes() == before
    assert sorted(path.name for path in home.iterdir()) == ["tapedeck.db"]


def test_a_long_section_is_cut_at_a_word_boundary():
    text = "word " * 1000
    cut = retrieve.excerpt(text)
    assert len(cut) <= retrieve.EXCERPT_CHARS + 2
    assert cut.endswith("…")
    assert "wor …" not in cut


# --- the prompt (SPEC-ask-002) ----------------------------------------------


def test_prompt_carries_question_sources_and_the_rules():
    text = citations.prompt("what is the core idea", [source()])
    assert "Question: what is the core idea" in text
    assert "The core idea is regeneration over maintenance." in text
    assert "[1]" in text
    assert "not in the library" in text
    assert "Use only what the sources say" in text


def test_prompt_numbers_sources_in_retrieval_order():
    text = citations.prompt("q", [source(), source(start_s=0, section="Intro", text="hello")])
    assert text.index("[1]") < text.index("[2]")
    assert "[2] Test Video: Building Things — Fixture Channel @ 0:00:00 (Intro)" in text


# --- the citation gate -------------------------------------------------------


def test_markers_within_the_retrieved_set_pass():
    assert citations.invented("a [1] b [2].", 2) == []


def test_markers_outside_the_retrieved_set_are_caught():
    assert citations.invented("confident [9] and [0].", 2) == [0, 9]


def test_sources_block_follows_the_citation_contract():
    assert citations.sources_block([source()]) == (
        "Sources:\n"
        "[1] Test Video: Building Things — Fixture Channel @ 0:01:35\n"
        "    https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"
    )


def test_a_channelless_page_still_renders_a_clean_citation():
    assert "[1] Test Video: Building Things @ 0:01:35" in citations.sources_block(
        [source(channel="")]
    )


# --- the seam ----------------------------------------------------------------


def test_missing_ask_section_is_a_config_error(tmp_path):
    (tmp_path / "config.toml").write_text("# nothing here\n")
    with pytest.raises(answerer.ConfigError, match="answerer"):
        answerer.seam(tmp_path)


def test_unparseable_config_is_a_config_error(tmp_path):
    (tmp_path / "config.toml").write_text("[ask\n")
    with pytest.raises(answerer.ConfigError):
        answerer.seam(tmp_path)


def test_the_prompt_reaches_the_answerer_on_stdin(tmp_path):
    answerer_script(tmp_path, '#!/bin/sh\ncat > "$TAPEDECK_HOME/seen"\necho drafted\n')
    assert answerer.run(answerer.seam(tmp_path), tmp_path, "the prompt") == "drafted"
    assert (tmp_path / "seen").read_text() == "the prompt"


def test_a_failing_answerer_is_an_answer_error(tmp_path):
    answerer_script(tmp_path, "#!/bin/sh\ncat > /dev/null\nexit 3\n")
    with pytest.raises(answerer.AnswerError, match="exited 3"):
        answerer.run(answerer.seam(tmp_path), tmp_path, "prompt")


def test_a_silent_answerer_is_an_answer_error(tmp_path):
    answerer_script(tmp_path, "#!/bin/sh\ncat > /dev/null\n")
    with pytest.raises(answerer.AnswerError):
        answerer.run(answerer.seam(tmp_path), tmp_path, "prompt")


def test_an_answerer_ignoring_stdin_does_not_break_the_pipe(tmp_path):
    answerer_script(tmp_path, "#!/bin/sh\necho ignored\n")
    assert answerer.run(answerer.seam(tmp_path), tmp_path, "x" * 200_000) == "ignored"


# --- the boundary ------------------------------------------------------------


def run_main(home, monkeypatch, argv):
    monkeypatch.setenv("TAPEDECK_HOME", str(home))
    return main(argv)


def test_answer_is_prose_then_tapedeck_sources(home, monkeypatch, capsys):
    answerer_script(home, "#!/bin/sh\ncat > /dev/null\necho 'regeneration wins [1].'\n")
    assert run_main(home, monkeypatch, ["run", "what is the core idea", "-k", "3"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("regeneration wins [1].\n\nSources:\n")
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in out


def test_the_cli_alias_is_the_same_verb(home, monkeypatch, capsys):
    answerer_script(home, "#!/bin/sh\ncat > /dev/null\necho 'yes [1].'\n")
    assert run_main(home, monkeypatch, ["answer", "-k", "2", "--", "core", "idea"]) == 0
    assert "Sources:" in capsys.readouterr().out


def test_no_sources_stops_before_the_answerer(home, monkeypatch, capsys):
    answerer_script(home, '#!/bin/sh\ntouch "$TAPEDECK_HOME/ran"\necho hi\n')
    assert run_main(home, monkeypatch, ["run", "xylophone quantum blockchain"]) == 1
    assert "no sources in the library" in capsys.readouterr().err
    assert not (home / "ran").exists()


def test_an_invented_citation_is_refused(home, monkeypatch, capsys):
    answerer_script(home, "#!/bin/sh\ncat > /dev/null\necho 'confident [9].'\n")
    assert run_main(home, monkeypatch, ["run", "core idea"]) == 1
    captured = capsys.readouterr()
    assert "citation" in captured.err
    assert "confident" not in captured.out


def test_an_unconfigured_answerer_is_a_usage_error(home, monkeypatch, capsys):
    (home / "config.toml").write_text("# no ask section\n")
    assert run_main(home, monkeypatch, ["run", "core idea"]) == 2
    assert "answerer" in capsys.readouterr().err


def test_config_is_checked_before_the_index_is_touched(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.toml").write_text("# no ask section\n")
    assert run_main(tmp_path, monkeypatch, ["run", "core idea"]) == 2


def test_k_must_be_at_least_one(home, monkeypatch, capsys):
    answerer_script(home, "#!/bin/sh\necho hi\n")
    assert run_main(home, monkeypatch, ["run", "core idea", "-k", "0"]) == 2
    assert "-k" in capsys.readouterr().err
