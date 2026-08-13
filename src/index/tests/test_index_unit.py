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


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "archive").mkdir(parents=True)
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return h


def write_page(home, name=None, text=PAGE):
    path = home / "archive" / f"{name or 'dQw4w9WgXcQ'}.md"
    path.write_text(text)
    return path


# ---------------------------------------------------------------- pages.py


def test_parse_reads_metadata_and_sections():
    page = parse(PAGE, stem="dQw4w9WgXcQ")
    assert page.video_id == "dQw4w9WgXcQ"
    assert page.title == "Test Video: Building Things"  # quoted scalar, colon kept
    assert page.channel == "Fixture Channel"
    assert page.duration_s == 720
    assert [s.start_s for s in page.sections] == [0, 95]
    assert page.sections[0].title == "Intro"
    # Paragraph breaks survive; the trailing blank line does not.
    assert page.sections[0].text == "Welcome to the fixture show.\n\nWe keep talking."


def test_section_start_prefers_the_deep_link_over_the_stamp():
    text = "---\nid: dQw4w9WgXcQ\n---\n\n## [9:99:99](https://y/watch?v=dQw4w9WgXcQ&t=42s) T\n\nx\n"
    assert parse(text).sections[0].start_s == 42


def test_section_start_falls_back_to_the_stamp():
    text = "---\nid: dQw4w9WgXcQ\n---\n\n## [1:02:03](https://y/watch?v=dQw4w9WgXcQ) T\n\nx\n"
    assert parse(text).sections[0].start_s == 3723


def test_section_with_no_readable_start_is_dropped_not_guessed():
    text = "---\nid: dQw4w9WgXcQ\n---\n\n## [later](nowhere) T\n\nbody\n"
    assert parse(text).sections == ()


def test_unclosed_frontmatter_is_a_page_error():
    with pytest.raises(PageError, match="never closed"):
        parse("---\nid: dQw4w9WgXcQ\ntitle: x\n")


def test_filename_wins_no_argument_with_frontmatter():
    with pytest.raises(PageError, match="does not match the filename"):
        parse(PAGE, stem="plainvide00")


def test_missing_id_is_a_page_error():
    with pytest.raises(PageError, match="no usable video id"):
        parse("---\ntitle: x\n---\n\n## [0:00:00](?t=0s) T\n\nbody\n")


def test_id_may_come_from_the_filename_alone():
    assert parse("## [0:00:00](?t=0s) T\n\nbody\n", stem="plainvide00").video_id == "plainvide00"


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0:00:00"), (95, "0:01:35"), (3600, "1:00:00"), (3723, "1:02:03"), (-5, "0:00:00")],
)
def test_hms_renders_hours_unpadded(seconds, expected):
    assert hms(seconds) == expected


def test_scalar_unescapes_a_quoted_value():
    assert scalar(' "a \\"b\\"\\nc" ') == 'a "b"\nc'


def test_missing_duration_is_none_not_zero():
    assert parse("---\nid: dQw4w9WgXcQ\nduration_s: n/a\n---\n").duration_s is None


# ---------------------------------------------------------------- store.py


def test_fts_query_never_lets_punctuation_become_syntax():
    assert fts_query("C++ don't --force") == '"C++" AND "don\'t" AND "--force"'
    assert fts_query('"exact phrase" tail') == '"exact phrase" AND "tail"'
    assert fts_query("sour*") == '"sour"*'
    assert fts_query("!!! ???") == ""


def test_fts_query_escapes_an_embedded_quote():
    assert fts_query('say"hi') == '"say""hi"'


def indexed(home, pages=None):
    return build(home, pages if pages is not None else [parse(PAGE, stem="dQw4w9WgXcQ")])


def test_build_is_atomic_and_leaves_no_temp_files(home):
    indexed(home)
    assert (home / DB_NAME).is_file()
    assert [p.name for p in home.iterdir() if p.name.startswith(f".{DB_NAME}")] == []


def test_a_failed_build_leaves_the_old_index_standing(home):
    indexed(home)
    before = store.search(home, "regeneration", 8)
    with pytest.raises(AttributeError):  # not a page — the writer chokes mid-build
        build(home, [parse(PAGE, stem="dQw4w9WgXcQ"), object()])
    assert store.search(home, "regeneration", 8) == before
    assert [p.name for p in home.iterdir() if p.name.startswith(f".{DB_NAME}")] == []


def test_search_carries_every_spec_index_002_field(home):
    indexed(home)
    (top,) = [r for r in store.search(home, "regeneration", 8)]
    assert top == {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video: Building Things",
        "section": "The Core Idea",
        "start_s": 95,
        "timestamp": "0:01:35",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s",
        "excerpt": "The core idea is regeneration over maintenance.",
    }


def test_search_without_a_database_is_unusable_not_empty(home):
    with pytest.raises(store.Unusable):
        store.search(home, "anything", 8)


def test_a_query_of_pure_punctuation_needs_no_database(home):
    assert store.search(home, "!!!", 8) == []


def test_section_titles_outrank_prose(home):
    page = parse(PAGE, stem="dQw4w9WgXcQ")
    indexed(home, [page])
    assert store.search(home, "core", 8)[0]["section"] == "The Core Idea"


def test_replace_video_reports_no_index_rather_than_making_one(home):
    assert replace_video(home, "dQw4w9WgXcQ", None) is None
    assert not (home / DB_NAME).exists()


def test_replace_video_with_no_page_drops_its_rows(home):
    indexed(home)
    assert replace_video(home, "dQw4w9WgXcQ", None) == home / DB_NAME
    assert store.search(home, "regeneration", 8) == []


# ------------------------------------------------- stemming (SPEC-index-003)

STEM_PAGE = """---
id: dQw4w9WgXcQ
title: "Stems"
---

## [0:00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s) Intro

We are archiving videos about transcribing meetings.
"""


@pytest.mark.parametrize(
    "query", ["video", "videos", "archive", "archived", "transcribe", "meeting", "meetings"]
)
def test_morphological_variants_match_in_both_directions(home, query):
    build(home, [parse(STEM_PAGE, stem="dQw4w9WgXcQ")])
    assert store.search(home, query, 8), f"{query!r} found nothing"


def test_stemming_does_not_make_everything_match(home):
    build(home, [parse(STEM_PAGE, stem="dQw4w9WgXcQ")])
    assert store.search(home, "xylophone", 8) == []


def test_the_index_records_the_tokenizer_it_was_built_with(home):
    build(home, [parse(STEM_PAGE, stem="dQw4w9WgXcQ")])
    with sqlite3.connect(home / DB_NAME) as db:
        (ddl,) = db.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks'").fetchone()
    assert "porter" in ddl


def make_pre_porter_db(home):
    """A database in the shape this component shipped before SPEC-index-003."""
    db = sqlite3.connect(home / DB_NAME)
    with db:
        db.executescript(store.SCHEMA.replace(f"'{store.TOKENIZE}'", "'unicode61'"))
        db.execute("PRAGMA user_version = 1")
        db.execute(
            "INSERT INTO chunks (video_id, start_s, section, text) VALUES (?, ?, ?, ?)",
            ("dQw4w9WgXcQ", 0, "Intro", "We are archiving videos."),
        )
    db.close()


def test_a_pre_porter_database_is_refused_rather_than_queried(home):
    make_pre_porter_db(home)
    with pytest.raises(store.Unusable):
        store.search(home, "videos", 8)


def test_update_migrates_a_pre_porter_database_by_rebuilding(home):
    make_pre_porter_db(home)
    write_page(home, text=STEM_PAGE)
    assert update(home, "dQw4w9WgXcQ") == 0
    assert store.search(home, "video", 8), "the rebuilt index must stem"


def test_update_migrates_a_database_whose_version_alone_looks_current(home):
    """The tokenizer is read off the database, not inferred from user_version."""
    make_pre_porter_db(home)
    with sqlite3.connect(home / DB_NAME) as db:
        db.execute(f"PRAGMA user_version = {store.SCHEMA_VERSION}")
    write_page(home, text=STEM_PAGE)
    assert update(home, "dQw4w9WgXcQ") == 0
    assert store.search(home, "video", 8)


# ---------------------------------------------------------------- __main__.py


def test_reindex_reports_the_database_path_on_stdout(home, capsys):
    write_page(home)
    assert reindex(home) == 0
    assert capsys.readouterr().out.strip() == str(home / DB_NAME)


def test_reindex_with_no_archive_directory_still_builds(home, capsys):
    (home / "archive").rmdir()
    assert reindex(home) == 0
    assert (home / DB_NAME).is_file()
    assert store.search(home, "anything", 8) == []


def test_a_broken_page_fails_the_run_but_not_the_index(home, capsys):
    write_page(home)
    (home / "archive" / "plainvide00.md").write_text("---\nid: nope\n---\n")
    assert reindex(home) == 1
    assert "plainvide00.md" in capsys.readouterr().err
    assert store.search(home, "regeneration", 8), "good pages still made it in"


def test_update_rejects_a_non_video_id(home):
    with pytest.raises(Failure) as exc:
        update(home, "not-an-id")
    assert exc.value.code == 2


def test_update_without_a_page_drops_the_video(home, capsys):
    write_page(home)
    reindex(home)
    (home / "archive" / "dQw4w9WgXcQ.md").unlink()
    assert update(home, "dQw4w9WgXcQ") == 0
    assert "dropping its rows" in capsys.readouterr().err
    assert store.search(home, "regeneration", 8) == []


def test_update_on_a_broken_page_refuses_rather_than_half_indexing(home):
    write_page(home)
    reindex(home)
    write_page(home, text="---\nid: dQw4w9WgXcQ\ntitle: x\n")  # unclosed frontmatter
    with pytest.raises(Failure):
        update(home, "dQw4w9WgXcQ")
    assert store.search(home, "regeneration", 8), "the old rows survived"


def test_update_with_no_database_builds_the_whole_index(home, capsys):
    write_page(home)
    assert update(home, "dQw4w9WgXcQ") == 0
    assert store.search(home, "regeneration", 8)


def test_search_rejects_a_zero_k(home):
    with pytest.raises(Failure) as exc:
        search(home, "x", 0, False)
    assert exc.value.code == 2


def test_search_on_a_corrupt_database_points_at_reindex(home):
    (home / DB_NAME).write_bytes(b"not a database")
    with pytest.raises(Failure, match="reindex"):
        search(home, "x", 8, False)


def test_no_matches_prints_nothing_and_json_prints_an_empty_list(home, capsys):
    write_page(home)
    reindex(home)
    capsys.readouterr()
    assert search(home, "xylophone", 8, False) == 0
    assert capsys.readouterr().out == ""
    assert search(home, "xylophone", 8, True) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_human_output_shows_timestamp_section_and_link(home, capsys):
    write_page(home)
    reindex(home)
    capsys.readouterr()
    search(home, "regeneration", 8, False)
    out = capsys.readouterr().out
    assert "0:01:35" in out
    assert "The Core Idea" in out
    assert "watch?v=dQw4w9WgXcQ&t=95s" in out


def test_main_search_joins_a_multi_word_query(home, capsys):
    write_page(home)
    reindex(home)
    capsys.readouterr()
    assert main(["search", "core", "idea", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["start_s"] == 95


def test_main_defaults_to_eight_results(home, capsys):
    sections = "\n".join(
        f"## [0:00:0{i}](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t={i}s) S{i}\n\nrepeated word\n"
        for i in range(12)
    )
    write_page(home, text=f"---\nid: dQw4w9WgXcQ\n---\n\n{sections}")
    reindex(home)
    capsys.readouterr()
    main(["search", "repeated", "--json"])
    assert len(json.loads(capsys.readouterr().out)) == 8


def test_main_reports_a_usage_error_as_exit_two(home, capsys):
    assert main(["update", "nope"]) == 2
    assert "error:" in capsys.readouterr().err
