"""Durable evals: ask --fast holds tapedeck.db to the index's shape (SPEC-ask-004).

Boundary: `python -m ask run "<question>" --fast`, library via $TAPEDECK_HOME,
answerer seam pinned by conftest.set_answerer.

Fast mode reads the database instead of shelling out to the index, which means it
also inherits the index's duty to refuse a database it does not understand. The two
databases below are the two ways that happens in the field: one left behind by an
older schema, one stemmed by an older tokenizer. Both still answer SQL — that is the
danger — so `tapedeck search` refusing while `ask --fast` answers is exactly what
these pin against.
"""

import sqlite3

from conftest import (
    CHAPTERED_META,
    PLAIN_META,
    run_component,
    set_answerer,
    write_archive_page,
)

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
]
BREAD_SECTIONS = [(0, "Part 1", "Block one content about sourdough starters.")]

QUESTION = "what is the core idea"

ANSWER_OK = """#!/bin/sh
cat > "$TAPEDECK_HOME/prompt-seen"
printf 'The library says regeneration beats maintenance [1].\\n'
"""

# A database of the old shape: the columns ask selects, rows that match the question,
# and a tokenizer this build does not stem under. Written out rather than derived so
# the fixture stays fixed while the index's own schema moves on.
STALE_SCHEMA = """
CREATE TABLE videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT '',
    upload_date TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    duration_s  INTEGER
);
CREATE VIRTUAL TABLE chunks USING fts5(
    video_id UNINDEXED, start_s UNINDEXED, section, text,
    tokenize = 'unicode61'
);
"""


def ask(home, *args):
    return run_component("ask", ["run", *args], home)


def indexed_home(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr
    set_answerer(home, ANSWER_OK)


def db(home):
    return home / "tapedeck.db"


def write_stale_tokenizer_db(home):
    """A pre-porter database that is otherwise perfectly answerable."""
    path = db(home)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    with con:
        con.executescript(STALE_SCHEMA)
        # Current version number, older stemming: the trap a version check alone
        # walks straight into (SPEC-index-003).
        con.execute("PRAGMA user_version = 2")
        con.execute(
            "INSERT INTO videos (video_id, title, channel) VALUES (?, ?, ?)",
            (CHAPTERED_META["id"], CHAPTERED_META["title"], CHAPTERED_META["channel"]),
        )
        con.execute(
            "INSERT INTO chunks (video_id, start_s, section, text) VALUES (?, ?, ?, ?)",
            (CHAPTERED_META["id"], 95, "The Core Idea", "The core idea is regeneration."),
        )
    # The fixture must be answerable, or a refusal below proves nothing about the gate.
    rows = con.execute('SELECT text FROM chunks WHERE chunks MATCH "core"').fetchall()
    con.close()
    assert rows, "fixture is not a database ask could have answered from"


def test_fast_refuses_a_database_from_another_schema_version(home):
    indexed_home(home)
    con = sqlite3.connect(db(home))
    with con:
        con.execute("PRAGMA user_version = 1")
    con.close()

    searched = run_component("index", ["search", "core idea"], home)
    assert searched.returncode != 0, "precondition: the index itself refuses this db"

    r = ask(home, QUESTION, "--fast")
    assert r.returncode == 1, "ask must not answer where search refuses"
    assert "reindex" in r.stderr.lower(), r.stderr
    assert not (home / "prompt-seen").exists(), "the answerer must never be invoked"


def test_fast_refuses_a_database_stemmed_by_another_tokenizer(home):
    indexed_home(home)
    write_stale_tokenizer_db(home)

    r = ask(home, QUESTION, "--fast")
    assert r.returncode == 1, "rows stemmed elsewhere are not rows this build matches"
    assert "reindex" in r.stderr.lower(), r.stderr
    assert not (home / "prompt-seen").exists(), "the answerer must never be invoked"
