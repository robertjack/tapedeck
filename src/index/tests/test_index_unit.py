"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/index/ are the real contract.
Run with: uv run --with pytest pytest src/index/tests -q
"""

import json
import sqlite3

import pytest

import index.store as store
from index.__main__ import Failure, main, reindex, search, update
from index.pages import PageError, Section, hms, parse, scalar
from index.store import DB_NAME, build, fts_query, replace_video

PAGE = """---
id: dQw4w9WgXcQ
title: "Test Video: Building Things"
channel: Fixture Channel
upload_date: 2026-01-15
duration_s: 720
url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
---

# Test Video: Building Things

Fixture Channel · 2026-01-15 · 0:12:00 · https://www.youtube.com/watch?v=dQw4w9WgXcQ

## [0:00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s) Intro

Welcome to the fixture show.

We keep talking.

## [0:01:35](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s) The Core Idea

The core idea is regeneration over maintenance.
"""


HEAD = "---\nid: plainvide00\ntitle: Sourdough Basics\n---\n\n"


def page(text=PAGE, stem="dQw4w9WgXcQ"):
    return parse(text, stem=stem)


# --- parsing ----------------------------------------------------------------


def test_frontmatter_and_sections():
    parsed = page()
    assert parsed.video_id == "dQw4w9WgXcQ"
    assert parsed.title == "Test Video: Building Things"
    assert parsed.channel == "Fixture Channel"
    assert parsed.duration_s == 720
    assert [(s.start_s, s.title) for s in parsed.sections] == [(0, "Intro"), (95, "The Core Idea")]


def test_body_before_the_first_section_is_not_a_chunk():
    assert "Fixture Channel ·" not in "".join(s.text for s in page().sections)


def test_paragraphs_survive_and_blank_runs_collapse():
    assert page().sections[0].text == "Welcome to the fixture show.\n\nWe keep talking."


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("plain", "plain"),
        ('  "Test Video: Building Things"  ', "Test Video: Building Things"),
        (r'"say \"hi\"\nagain"', 'say "hi"\nagain'),
        (r'"back\\slash"', "back\\slash"),
        ('"2026"', "2026"),
    ],
)
def test_scalar_reads_back_what_the_renderer_wrote(raw, expected):
    assert scalar(raw) == expected


def test_section_start_prefers_the_deep_link_then_the_stamp():
    lying = PAGE.replace("[0:01:35]", "[9:99:99]")
    assert page(lying).sections[1].start_s == 95
    linkless = HEAD + "## [1:01:01](notalink) Late\n\nwords\n"
    assert page(linkless, stem=None).sections == (Section(3661, "Late", "words"),)


def test_a_heading_with_no_recoverable_time_is_dropped():
    assert page(HEAD + "## [](nolink) Late\n\nwords\n", stem=None).sections == ()


def test_untitled_sections_are_kept():
    plain = "## [0:05:00](https://www.youtube.com/watch?v=plainvide00&t=300s)\n\nblock two\n"
    assert page(HEAD + plain, stem=None).sections == (Section(300, "", "block two"),)


def test_a_page_with_no_sections_parses_to_no_chunks():
    assert page(PAGE.split("## ")[0], stem="dQw4w9WgXcQ").sections == ()


def test_pages_without_a_trustworthy_id_are_refused():
    with pytest.raises(PageError):
        page(stem="zzzzzzzzzzz")  # frontmatter id disagrees with the filename
    with pytest.raises(PageError):
        page("---\nid: dQw4w9WgXcQ\n\n# no closing fence\n", stem="dQw4w9WgXcQ")
    with pytest.raises(PageError):
        page("## [0:00:00](x) t\n\nwords\n", stem=None)  # no id anywhere


@pytest.mark.parametrize(
    "seconds,expected", [(0, "0:00:00"), (95, "0:01:35"), (3661, "1:01:01"), (-5, "0:00:00")]
)
def test_hms(seconds, expected):
    assert hms(seconds) == expected


# --- query building ---------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        ("regeneration", '"regeneration"'),
        ("core idea", '"core" AND "idea"'),
        ('"core idea"', '"core idea"'),
        ("regen*", '"regen"*'),
        ("don't -- stop", '"don\'t" AND "stop"'),
        ('say "hi', '"say" AND "hi"'),
        ("   ", ""),
        ("--", ""),
    ],
)
def test_fts_query_never_produces_syntax(query, expected):
    assert fts_query(query) == expected


@pytest.mark.parametrize("query", ["a*b", '"', "NEAR(", "x AND", "col:val", "^start", "(", "*"])
def test_hostile_queries_still_execute(home, query):
    reindex(home)
    store.search(home, query, 8)  # must not raise


# --- store ------------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "archive").mkdir(parents=True)
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return h


def install(home, text=PAGE, video_id="dQw4w9WgXcQ"):
    (home / "archive" / f"{video_id}.md").write_text(text)


def test_build_is_atomic_and_leaves_no_temp_file(home, monkeypatch):
    install(home)
    reindex(home)
    survivor = (home / DB_NAME).read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError):
        build(home, [page()])
    assert (home / DB_NAME).read_bytes() == survivor
    assert [p.name for p in home.iterdir() if p.name != "archive"] == [DB_NAME]


def test_update_without_a_database_falls_back_to_a_full_build(home):
    install(home)
    assert not (home / DB_NAME).exists()
    assert update(home, "dQw4w9WgXcQ") == 0
    assert store.search(home, "regeneration", 8)


def test_update_drops_a_video_whose_page_is_gone(home):
    install(home)
    reindex(home)
    (home / "archive" / "dQw4w9WgXcQ.md").unlink()
    assert update(home, "dQw4w9WgXcQ") == 0
    assert store.search(home, "regeneration", 8) == []


def test_a_stale_schema_is_rebuilt_not_trusted(home):
    install(home)
    reindex(home)
    with sqlite3.connect(home / DB_NAME) as db:
        db.execute(f"PRAGMA user_version = {store.SCHEMA_VERSION + 1}")
    assert replace_video(home, "dQw4w9WgXcQ", page()) is None
    with pytest.raises(store.Unusable):
        store.search(home, "regeneration", 8)
    assert update(home, "dQw4w9WgXcQ") == 0  # ...and the verb recovers on its own
    assert store.search(home, "regeneration", 8)


def test_a_corrupt_database_is_reported_not_ignored(home):
    (home / DB_NAME).write_bytes(b"not a database at all")
    with pytest.raises(Failure) as caught:
        search(home, "anything", 8, False)
    assert caught.value.code == 1
    assert "reindex" in str(caught.value)


def test_search_ranks_section_titles_above_prose(home):
    install(home)
    other = PAGE.replace("dQw4w9WgXcQ", "plainvide00").replace(
        "## [0:01:35](https://www.youtube.com/watch?v=plainvide00&t=95s) The Core Idea",
        "## [0:01:35](https://www.youtube.com/watch?v=plainvide00&t=95s) Regeneration",
    )
    install(home, other, "plainvide00")
    reindex(home)
    assert store.search(home, "regeneration", 8)[0]["video_id"] == "plainvide00"


def test_results_carry_the_whole_contract(home):
    install(home)
    reindex(home)
    top = store.search(home, "regeneration", 8)[0]
    assert top == {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video: Building Things",
        "section": "The Core Idea",
        "start_s": 95,
        "timestamp": "0:01:35",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s",
        "excerpt": "The core idea is regeneration over maintenance.",
    }


def test_excerpts_are_one_line(home):
    install(home)
    reindex(home)
    assert "\n" not in store.search(home, "fixture", 8)[0]["excerpt"]


def test_multiple_words_are_an_and(home):
    install(home)
    reindex(home)
    assert store.search(home, "core regeneration", 8)
    assert store.search(home, "core sourdough", 8) == []


# --- boundary ---------------------------------------------------------------


def test_reindex_on_an_empty_home_still_makes_a_searchable_index(home, capsys):
    (home / "archive").rmdir()
    assert main(["reindex"]) == 0
    capsys.readouterr()
    assert main(["search", "anything", "--json"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_a_broken_page_is_reported_and_the_rest_still_index(home, capsys):
    install(home)
    install(home, "---\nid: nope\n", "brokenpage0")
    assert main(["reindex"]) == 1
    assert "brokenpage0" in capsys.readouterr().err
    assert store.search(home, "regeneration", 8)


def test_human_output_shows_time_title_section_and_link(home, capsys):
    install(home)
    reindex(home)
    capsys.readouterr()
    assert main(["search", "regeneration"]) == 0
    out = capsys.readouterr().out
    assert "0:01:35  Test Video: Building Things — The Core Idea" in out
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in out


def test_query_words_are_joined(home, capsys):
    install(home)
    reindex(home)
    capsys.readouterr()
    assert main(["search", "core", "idea", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_bad_k_and_bad_id_are_usage_errors(home):
    with pytest.raises(Failure) as caught:
        search(home, "x", 0, False)
    assert caught.value.code == 2
    with pytest.raises(Failure) as caught:
        update(home, "too-short")
    assert caught.value.code == 2


def test_missing_index_is_an_operation_failure(home, capsys):
    assert main(["search", "anything"]) == 1
    assert "reindex" in capsys.readouterr().err


def test_unknown_verb_exits_two(home):
    with pytest.raises(SystemExit) as caught:
        main(["polish"])
    assert caught.value.code == 2
