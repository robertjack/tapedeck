"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/ask/ are the real contract.
Run with: uv run --with pytest pytest src/ask/tests -q
"""

import json

import pytest

from ask.citations import (
    INSTRUCTIONS,
    deep_links,
    document,
    hms,
    invented,
    prompt,
    sources_block,
    unverified,
)
from ask.library import videos
from ask.retrieve import Source, excerpt, match_expression, terms, top_k
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


# --- library ---


def test_videos_maps_ids_to_durations(home):
    add(home, "dQw4w9WgXcQ", 720)
    add(home, "plainvide00", 90.6)
    assert videos(home) == {"dQw4w9WgXcQ": 720, "plainvide00": 90}


def test_videos_is_empty_without_a_library(tmp_path):
    assert videos(tmp_path / "nowhere") == {}


def test_entry_without_usable_meta_is_present_with_unknown_duration(home):
    add(home, "dQw4w9WgXcQ", meta=False)
    (home / "library" / "brokenvid00").mkdir()
    (home / "library" / "brokenvid00" / "meta.json").write_text("{not json")
    (home / "library" / "notanid").mkdir()  # ignored: not an 11-char video id
    assert videos(home) == {"brokenvid00": None, "dQw4w9WgXcQ": None}


# --- citation verification (librarian mode) ---


def test_deep_links_reads_id_and_offset_out_of_markdown():
    text = "See [intro](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s), and that's it."
    assert deep_links(text) == [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s", "dQw4w9WgXcQ", 95)
    ]


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://youtu.be/dQw4w9WgXcQ?t=30", ("dQw4w9WgXcQ", 30)),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1h2m3s", ("dQw4w9WgXcQ", 3723)),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", ("dQw4w9WgXcQ", None)),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=later", ("dQw4w9WgXcQ", None)),
    ],
)
def test_deep_links_handles_the_forms_youtube_writes(url, expected):
    assert deep_links(f"prose {url} prose")[0][1:] == expected


def test_no_links_at_all_is_no_citations():
    assert deep_links("A confident answer with no citations at all.") == []


def test_unverified_names_fabricated_and_overrunning_citations():
    known = {"dQw4w9WgXcQ": 720, "plainvide00": None}
    links = deep_links(
        "a https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s "
        "b https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=720s "
        "c https://www.youtube.com/watch?v=plainvide00&t=99999s "  # duration unknown: stands
        "d https://www.youtube.com/watch?v=nosuchvid00&t=10s "
        "e https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9999s"
    )
    problems = unverified(links, known)
    assert len(problems) == 2
    assert "nosuchvid00" in problems[0]
    assert "2:46:39" in problems[1] and "0:12:00" in problems[1]


# --- the numbering (fast mode) ---


def test_prompt_carries_the_rules_the_numbering_and_the_question():
    text = prompt("what is the core idea", [SRC, BARE])
    assert INSTRUCTIONS in text
    assert "not in the library" in text
    assert "[1] Test Video — Fixture Channel @ 0:01:35 (The Core Idea)" in text
    assert "[2] Sourdough @ 0:00:00" in text  # no channel, no section: no empty furniture
    assert SRC.text in text
    assert text.rstrip().endswith("Question: what is the core idea")


def test_sources_block_lists_every_retrieved_chunk_with_its_deep_link():
    block = sources_block([SRC])
    assert "[1] Test Video — Fixture Channel @ 0:01:35" in block
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in block


def test_invented_finds_only_markers_that_were_never_offered():
    assert invented("grounded [1] and [2]", 2) == []
    assert invented("stray [9] and [3]", 2) == [3, 9]
    assert invented("no markers here", 2) == []


def test_document_is_prose_then_sources():
    out = document("  An answer [1].  ", [SRC])
    assert out.startswith("An answer [1].\n\nSources:")


def test_hms_leaves_hours_unpadded():
    assert (hms(0), hms(95), hms(3723), hms(-4)) == ("0:00:00", "0:01:35", "1:02:03", "0:00:00")


# --- retrieval ---


def test_terms_drop_grammar_but_never_everything():
    assert terms("what is the core idea") == ["core", "idea"]
    assert terms("what is it") == ["what", "is", "it"]  # nothing left to keep: keep it all
    assert terms('"why not" the thing') == ["why not", "thing"]
    assert terms("???") == []


def test_match_expression_ors_quoted_phrases():
    assert match_expression("what is the core idea") == '"core" OR "idea"'
    assert match_expression("C++ don't") == '"C++" OR "don\'t"'
    assert match_expression("???") == ""


def test_excerpt_cuts_long_text_at_a_word_boundary():
    assert excerpt("  short  ") == "short"
    long = " ".join(["word"] * 900)
    cut = excerpt(long)
    assert cut.endswith(" …") and len(cut) <= 1602 and "wor …" not in cut


def test_unanswerable_query_never_opens_the_database(home):
    assert top_k(home, "???", 8) == []  # no index here at all — and none is needed


# --- seams ---


def test_command_reads_the_configured_seam(home):
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text('[ask]\nlibrarian_command = " sh librarian.sh "\n')
    assert command(home, LIBRARIAN_KEY, "librarian") == "sh librarian.sh"
    with pytest.raises(ConfigError, match="answerer"):
        command(home, ANSWERER_KEY, "answerer")


@pytest.mark.parametrize("config", ["", "# nothing\n", "[ask]\nlibrarian_command = 4\n", "{{{"])
def test_a_seam_that_is_not_configured_is_a_config_error(home, config):
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(config)
    with pytest.raises(ConfigError):
        command(home, LIBRARIAN_KEY, "librarian")


def test_missing_brief_is_a_config_error(home):
    with pytest.raises(ConfigError, match="brief"):
        brief(home)
    (home / "CLAUDE.md").write_text("# brief\n")
    assert brief(home).name == "CLAUDE.md"


def test_run_hands_stdin_over_and_returns_stdout(home):
    out = run("cat; echo '  '", home, "the question", "librarian", cwd=home)
    assert out == "the question"


def test_run_in_the_library_home_sees_the_library_home(home):
    assert run("pwd", home, "", "librarian", cwd=home) == str(home)
    assert run('printf "%s" "$PWD $TAPEDECK_HOME"', home, "", "librarian", cwd=home) == (
        f"{home} {home}"
    )


@pytest.mark.parametrize("script", ["cat > /dev/null; exit 3", "cat > /dev/null"])
def test_a_seam_that_fails_or_says_nothing_has_not_answered(home, script):
    with pytest.raises(AnswerError, match="answerer"):
        run(script, home, "prompt", "answerer")
