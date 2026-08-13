"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/ask/ are the real contract.
Run with: uv run --with pytest pytest src/ask/tests -q
"""

import json
import sqlite3

import pytest

from ask.citations import (
    INSTRUCTIONS,
    ask_for,
    deep_link,
    deep_links,
    document,
    hms,
    invented,
    prompt,
    sources_block,
    unverified,
)
from ask.library import videos
from ask.retrieve import IndexUnreadable, Source, excerpt, match_expression, terms, top_k
from ask.seams import ANSWERER_KEY, LIBRARIAN_KEY, AnswerError, ConfigError, brief, command, run

SRC = Source(
    video_id="dQw4w9WgXcQ",
    title="Test Video",
    channel="Fixture Channel",
    section="The Core Idea",
    start_s=95,
    text="The core idea is regeneration over maintenance.",
)
BARE = Source("plainvide00", "Sourdough", "", "", 0, "Block one.")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    return h


def add(home, video_id, duration=720, meta=True):
    entry = home / "library" / video_id
    entry.mkdir(parents=True)
    if meta:
        (entry / "meta.json").write_text(json.dumps({"id": video_id, "duration_s": duration}))
    return entry


def build_index(home, rows):
    """A minimal stand-in for the index's database, at the schema it pins."""
    db = sqlite3.connect(home / "tapedeck.db")
    with db:
        db.execute(
            "CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT, channel TEXT,"
            " upload_date TEXT, url TEXT, duration_s INTEGER)"
        )
        db.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5(video_id UNINDEXED,"
            " start_s UNINDEXED, section, text, tokenize = 'porter unicode61')"
        )
        for video_id, start_s, section, text in rows:
            db.execute(
                "INSERT OR IGNORE INTO videos (video_id, title, channel) VALUES (?, ?, ?)",
                (video_id, f"Title of {video_id}", "Fixture Channel"),
            )
            db.execute(
                "INSERT INTO chunks (video_id, start_s, section, text) VALUES (?, ?, ?, ?)",
                (video_id, start_s, section, text),
            )
    db.close()


CHUNKS = [
    ("dQw4w9WgXcQ", 0, "Intro", "Welcome to the fixture show."),
    ("dQw4w9WgXcQ", 95, "The Core Idea", "The core idea is regeneration over maintenance."),
    ("plainvide00", 0, "Part 1", "Block one content about sourdough starters."),
    ("plainvide00", 300, "Part 2", "The core idea of proofing is patience."),
]


# --- library ---


def test_videos_maps_ids_to_durations(home):
    add(home, "dQw4w9WgXcQ", 720)
    add(home, "plainvide00", 90.6)
    assert videos(home) == {"dQw4w9WgXcQ": 720, "plainvide00": 90}


def test_videos_is_empty_without_a_library(tmp_path):
    assert videos(tmp_path / "nowhere") == {}


def test_unreadable_meta_still_counts_as_present(home):
    add(home, "dQw4w9WgXcQ", meta=False)
    add(home, "plainvide00").joinpath("meta.json").write_text("{not json")
    assert videos(home) == {"dQw4w9WgXcQ": None, "plainvide00": None}


def test_non_video_directories_are_ignored(home):
    add(home, "dQw4w9WgXcQ")
    (home / "library" / "scratch").mkdir()
    (home / "library" / "stray.txt").write_text("x")
    assert set(videos(home)) == {"dQw4w9WgXcQ"}


# --- retrieval ---


def test_terms_drop_question_grammar():
    assert terms("what is the core idea") == ["core", "idea"]


def test_terms_keep_everything_when_all_grammar():
    assert terms("what is it") == ["what", "is", "it"]


def test_terms_keep_quoted_groups_whole_even_when_grammar():
    assert terms('why "the thing"') == ["the thing"]


def test_match_expression_ors_and_quotes_every_word():
    assert match_expression("what is the core idea") == '"core" OR "idea"'


def test_match_expression_is_empty_for_wordless_questions():
    assert match_expression("??? ...") == ""


def test_match_expression_escapes_embedded_quotes():
    # A stray quote inside a word must be doubled, not left to end the phrase.
    assert match_expression('say"hi') == '"say""hi"'


def test_excerpt_cuts_long_text_at_a_word_boundary():
    cut = excerpt("word " * 1000)
    assert len(cut) < 1700 and cut.endswith("…") and "wor …" not in cut


def test_excerpt_leaves_short_text_alone():
    assert excerpt("  short one  ") == "short one"


def test_top_k_ranks_and_bounds(home):
    build_index(home, CHUNKS)
    found = top_k(home, "what is the core idea", 2)
    assert [s.section for s in found] == ["The Core Idea", "Part 2"]
    assert found[0].channel == "Fixture Channel"
    assert found[0].url == deep_link("dQw4w9WgXcQ", 95)


def test_top_k_scoped_returns_only_that_video(home):
    build_index(home, CHUNKS)
    found = top_k(home, "what is the core idea", 8, "plainvide00")
    assert {s.video_id for s in found} == {"plainvide00"}


def test_scoped_k_buys_k_chunks_of_the_scoped_video(home):
    build_index(home, CHUNKS)
    # Unscoped, the best two hits are both the other video's; scoping must not
    # simply filter them away and leave nothing.
    assert len(top_k(home, "core idea sourdough", 2, "plainvide00")) == 2


def test_top_k_scope_with_no_match_is_empty(home):
    build_index(home, CHUNKS)
    assert top_k(home, "sourdough starters", 8, "dQw4w9WgXcQ") == []


def test_top_k_on_a_wordless_question_never_opens_the_index(home):
    assert top_k(home, "???", 8) == []


def test_top_k_without_an_index_is_unreadable(home):
    with pytest.raises(IndexUnreadable):
        top_k(home, "anything", 8)


def test_top_k_on_a_foreign_database_is_unreadable(home):
    (home / "tapedeck.db").write_bytes(b"not a database")
    with pytest.raises(IndexUnreadable):
        top_k(home, "anything", 8)


# --- fast-mode citation contract ---


def test_hms_is_unpadded_hours():
    assert (hms(0), hms(95), hms(3725), hms(-4)) == ("0:00:00", "0:01:35", "1:02:05", "0:00:00")


def test_prompt_carries_the_rules_the_sources_and_the_question():
    text = prompt("what is the core idea", [SRC, BARE])
    assert INSTRUCTIONS in text
    assert "not in the library" in text
    assert "[1] Test Video — Fixture Channel @ 0:01:35 (The Core Idea)" in text
    assert "The core idea is regeneration over maintenance." in text
    assert "[2] Sourdough @ 0:00:00" in text
    assert text.endswith("Question: what is the core idea\n")


def test_sources_block_lists_every_retrieved_chunk_with_its_link():
    block = sources_block([SRC, BARE])
    assert block.startswith("Sources:")
    assert "[1] Test Video — Fixture Channel @ 0:01:35" in block
    assert "    https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in block
    assert "[2] Sourdough @ 0:00:00" in block


def test_invented_finds_markers_no_source_carries():
    assert invented("a [1] b [9] c [2]", 2) == [9]
    assert invented("a [1] b", 2) == []


def test_document_is_prose_then_sources():
    out = document("  Answer [1].  ", [SRC])
    assert out == "Answer [1].\n\nSources:\n[1] Test Video — Fixture Channel @ 0:01:35\n" + (
        "    https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"
    )


# --- librarian-mode verification ---


def test_ask_for_is_the_bare_question_when_unscoped():
    assert ask_for("what is this about", None) == "what is this about\n"


def test_ask_for_states_the_scope():
    text = ask_for("what is this about", "dQw4w9WgXcQ")
    assert "library/dQw4w9WgXcQ/" in text
    assert "archive/dQw4w9WgXcQ.md" in text
    assert text.endswith("what is this about\n")


def test_deep_links_reads_markdown_links_without_their_punctuation():
    found = deep_links("see [it](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s).")
    assert found == [("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s", "dQw4w9WgXcQ", 95)]


def test_deep_links_reads_youtu_be_and_clock_offsets():
    found = deep_links("a https://youtu.be/dQw4w9WgXcQ?t=1h2m3s b")
    assert found[0][1:] == ("dQw4w9WgXcQ", 3723)


def test_deep_links_without_a_timestamp_claim_no_moment():
    assert deep_links("https://www.youtube.com/watch?v=dQw4w9WgXcQ")[0][2] is None


def test_deep_links_ignores_other_urls():
    assert deep_links("https://example.com/watch?v=dQw4w9WgXcQ&t=1s") == []


def test_unverified_accepts_a_real_moment():
    links = deep_links(deep_link("dQw4w9WgXcQ", 95))
    assert unverified(links, {"dQw4w9WgXcQ": 720}) == []


def test_unverified_rejects_a_video_the_library_lacks():
    links = deep_links(deep_link("nosuchvid00", 10))
    assert "no video" in unverified(links, {"dQw4w9WgXcQ": 720})[0]


def test_unverified_rejects_a_moment_past_the_end():
    links = deep_links(deep_link("dQw4w9WgXcQ", 9999))
    assert "past the end" in unverified(links, {"dQw4w9WgXcQ": 720})[0]


def test_unverified_tolerates_an_unknown_duration():
    links = deep_links(deep_link("dQw4w9WgXcQ", 9999))
    assert unverified(links, {"dQw4w9WgXcQ": None}) == []


def test_unverified_rejects_a_real_video_outside_the_scope():
    links = deep_links(deep_link("plainvide00", 10))
    known = {"dQw4w9WgXcQ": 720, "plainvide00": 720}
    assert unverified(links, known) == []
    assert "outside the --video" in unverified(links, known, "dQw4w9WgXcQ")[0]


# --- seams ---


def test_command_reads_the_configured_seam(home):
    (home / "config.toml").write_text('[ask]\nlibrarian_command = " claude -p "\n')
    assert command(home, LIBRARIAN_KEY, "librarian") == "claude -p"


@pytest.mark.parametrize(
    "text", ["", "# nothing\n", "[ask]\nanswerer_command = 4\n", "[ask]\nanswerer_command = ''\n"]
)
def test_command_without_a_usable_value_is_a_config_error(home, text):
    (home / "config.toml").write_text(text)
    with pytest.raises(ConfigError):
        command(home, ANSWERER_KEY, "answerer")


def test_command_on_broken_toml_is_a_config_error(home):
    (home / "config.toml").write_text("[ask\n")
    with pytest.raises(ConfigError):
        command(home, ANSWERER_KEY, "answerer")


def test_brief_is_required(home):
    with pytest.raises(ConfigError):
        brief(home)
    (home / "CLAUDE.md").write_text("# brief\n")
    assert brief(home).name == "CLAUDE.md"


def test_run_returns_stdout_and_reports_where_it_ran(home):
    out = run("pwd; cat", home, "hello\n", "librarian", cwd=home)
    assert out.splitlines()[0] == str(home)
    assert "hello" in out


def test_run_exports_the_home(home):
    assert run('printf "%s" "$TAPEDECK_HOME"', home, "", "answerer") == str(home)


def test_run_on_a_failed_seam_raises(home):
    with pytest.raises(AnswerError):
        run("exit 3", home, "", "answerer")


def test_run_on_an_empty_answer_raises(home):
    with pytest.raises(AnswerError):
        run("cat > /dev/null", home, "q", "answerer")
