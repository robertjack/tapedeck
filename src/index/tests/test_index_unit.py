"""Ephemeral unit tests for the index internals (disposable, not the contract).

The durable acceptance criteria live in system/evals/index/ and drive the
subprocess boundary. These go under it: page parsing, query building, and the
schema-version gate at the level where each is written.

Run: uv run --no-project --with pytest pytest src/index/tests -q
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from index import store  # noqa: E402
from index.__main__ import main  # noqa: E402
from index.pages import PageError, Section, deep_link, hms, parse  # noqa: E402

PAGE = """---
id: dQw4w9WgXcQ
title: "Test Video: Building Things"
channel: Fixture Channel
upload_date: 2026-01-15
duration_s: 720
url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
---

# Test Video: Building Things

Fixture Channel · 2026-01-15 · 0:12:00

## [0:00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s) Intro

Welcome to the fixture show.

## [0:01:35](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s) The Core Idea

The core idea is regeneration over maintenance.

Second paragraph of the same section.
"""


# --- pages ------------------------------------------------------------------


def test_hms_is_unpadded_hours():
    assert hms(0) == "0:00:00"
    assert hms(95) == "0:01:35"
    assert hms(3725) == "1:02:05"
    assert hms(-5) == "0:00:00"


def test_deep_link_shape():
    assert deep_link("dQw4w9WgXcQ", 95.7) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"


def test_parse_reads_frontmatter_and_sections():
    page = parse(PAGE, stem="dQw4w9WgXcQ")
    assert page.video_id == "dQw4w9WgXcQ"
    assert page.title == "Test Video: Building Things"  # quoted scalar unescaped
    assert page.channel == "Fixture Channel"
    assert page.duration_s == 720
    assert [s.start_s for s in page.sections] == [0, 95]
    assert page.sections[0] == Section(0, "Intro", "Welcome to the fixture show.")
    assert page.sections[1].text.endswith("Second paragraph of the same section.")


def test_byline_before_the_first_heading_is_not_a_chunk():
    assert all("Fixture Channel ·" not in s.text for s in parse(PAGE).sections)


def test_untitled_section_keeps_its_text():
    page = parse(PAGE.replace("&t=0s) Intro", "&t=0s)"), stem="dQw4w9WgXcQ")
    assert page.sections[0] == Section(0, "", "Welcome to the fixture show.")


def test_stamp_is_the_fallback_when_the_link_carries_no_time():
    page = parse(PAGE.replace("&t=95s", ""), stem="dQw4w9WgXcQ")
    assert [s.start_s for s in page.sections] == [0, 95]


def test_escaped_scalars_round_trip():
    page = parse(PAGE.replace('"Test Video: Building Things"', '"a \\"b\\" \\\\ c"'))
    assert page.title == 'a "b" \\ c'


def test_id_mismatch_and_bad_id_are_refused():
    with pytest.raises(PageError):
        parse(PAGE, stem="plainvide00")
    with pytest.raises(PageError):
        parse("---\nid: nope\n---\n")
    with pytest.raises(PageError):
        parse("---\nid: dQw4w9WgXcQ\n")  # frontmatter never closed


def test_filename_supplies_the_id_when_frontmatter_has_none():
    page = parse("## [0:00:00](x?t=3s) T\n\nwords\n", stem="dQw4w9WgXcQ")
    assert page.video_id == "dQw4w9WgXcQ"
    assert page.sections == (Section(3, "T", "words"),)


# --- queries ----------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        ("core idea", '"core" AND "idea"'),
        ('"core idea"', '"core idea"'),
        ("regen*", '"regen"*'),
        ("--force", '"--force"'),
        ("!!! ???", ""),
        ('say "hi"', '"say" AND "hi"'),
    ],
)
def test_fts_query_never_becomes_syntax(query, expected):
    assert store.fts_query(query) == expected


# --- the schema-version gate (SPEC-index-004) -------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "archive").mkdir(parents=True)
    (h / "archive" / "dQw4w9WgXcQ.md").write_text(PAGE)
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return h


def user_version(home):
    con = sqlite3.connect(home / "tapedeck.db")
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def set_user_version(home, version):
    con = sqlite3.connect(home / "tapedeck.db")
    with con:
        con.execute(f"PRAGMA user_version = {version}")
    con.close()


def test_build_stamps_the_current_version(home):
    assert main(["reindex"]) == 0
    assert user_version(home) == store.SCHEMA_VERSION != 0


def test_open_current_separates_missing_from_foreign(home):
    with pytest.raises(store.Unusable) as missing:
        store.open_current(home / "tapedeck.db")
    assert missing.value.missing

    assert main(["reindex"]) == 0
    set_user_version(home, store.SCHEMA_VERSION + 7)
    with pytest.raises(store.Unusable) as foreign:
        store.open_current(home / "tapedeck.db")
    assert not foreign.value.missing
    assert str(store.SCHEMA_VERSION + 7) in str(foreign.value)


def test_a_file_that_is_no_database_is_refused_not_missing(home):
    (home / "tapedeck.db").write_text("not a database")
    with pytest.raises(store.Unusable) as exc:
        store.open_current(home / "tapedeck.db")
    assert not exc.value.missing


def test_another_tokenizer_is_refused_at_the_current_version(home):
    path = home / "tapedeck.db"
    con = sqlite3.connect(path)
    with con:
        con.executescript(store.SCHEMA.replace(store.TOKENIZE, "unicode61"))
        con.execute(f"PRAGMA user_version = {store.SCHEMA_VERSION}")
    con.close()
    with pytest.raises(store.Unusable, match="tokenizer"):
        store.open_current(path)


def test_update_without_an_index_builds_one(home, capsys):
    assert main(["update", "dQw4w9WgXcQ"]) == 0
    capsys.readouterr()
    assert main(["search", "regeneration", "--json"]) == 0
    assert "regeneration" in capsys.readouterr().out


def test_update_refuses_a_foreign_version(home, capsys):
    assert main(["reindex"]) == 0
    set_user_version(home, 1)
    capsys.readouterr()
    assert main(["update", "dQw4w9WgXcQ"]) == 1
    assert "reindex" in capsys.readouterr().err.lower()
    assert user_version(home) == 1, "a refused update must not have written"


def test_search_refuses_a_foreign_version_even_with_an_empty_query(home, capsys):
    assert main(["reindex"]) == 0
    set_user_version(home, 1)
    capsys.readouterr()
    assert main(["search", "!!!"]) == 1
    assert "reindex" in capsys.readouterr().err.lower()


def test_search_without_an_index_says_so(home, capsys):
    assert main(["search", "anything"]) == 1
    assert "reindex" in capsys.readouterr().err.lower()


def test_empty_query_over_a_good_index_is_quietly_empty(home, capsys):
    assert main(["reindex"]) == 0
    capsys.readouterr()
    assert main(["search", "!!!", "--json"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_bad_k_and_bad_id_are_usage_errors(home):
    assert main(["reindex"]) == 0
    assert main(["search", "core", "-k", "0"]) == 2
    assert main(["update", "nope"]) == 2


def test_reindex_over_a_foreign_version_migrates(home):
    assert main(["reindex"]) == 0
    set_user_version(home, 1)
    assert main(["reindex"]) == 0
    assert user_version(home) == store.SCHEMA_VERSION


def test_reindex_leaves_no_temp_files_and_reports_a_bad_page(home, capsys):
    (home / "archive" / "brokenvid00.md").write_text("---\nid: mismatch\n---\n")
    assert main(["reindex"]) == 1
    assert "brokenvid00" in capsys.readouterr().err
    assert not list(home.glob(".tapedeck.db*"))


def test_update_drops_rows_when_the_page_is_gone(home, capsys):
    assert main(["reindex"]) == 0
    (home / "archive" / "dQw4w9WgXcQ.md").unlink()
    assert main(["update", "dQw4w9WgXcQ"]) == 0
    capsys.readouterr()
    assert main(["search", "regeneration", "--json"]) == 0
    assert capsys.readouterr().out.strip() == "[]"
