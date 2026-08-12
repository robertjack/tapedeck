"""tapedeck.db: the SQLite FTS5 index over archive-page sections.

Sole writer of `$TAPEDECK_HOME/tapedeck.db` (library-layout write authority). The
file is disposable by design — `build` writes a fresh database beside the old one
and swaps it in, so an interrupted reindex leaves the previous index intact
(SPEC-core-003) and never a half-built one.

Ranking is bm25, ordered with explicit tie-breaks so that an incrementally
updated database answers exactly like a fully rebuilt one (SPEC-index-001):
insertion order — the one thing the two builds do not share — never leaks out.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .pages import Page, deep_link, hms

DB_NAME = "tapedeck.db"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT '',
    upload_date TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    duration_s  INTEGER
);

-- One row per archive-page section (SPEC-index-001). The searchable text is the
-- section title and its prose; id and start seconds ride along to address it.
CREATE VIRTUAL TABLE chunks USING fts5(
    video_id UNINDEXED,
    start_s UNINDEXED,
    section,
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

SNIPPET_TOKENS = 24  # fts5 caps this at 64
COLUMN_WEIGHTS = "0.0, 0.0, 2.0, 1.0"  # a hit in a section title beats one in prose
SEARCH_SQL = f"""
SELECT chunks.video_id                  AS video_id,
       chunks.start_s                   AS start_s,
       chunks.section                   AS section,
       COALESCE(videos.title, '')       AS title,
       snippet(chunks, 3, '', '', '…', {SNIPPET_TOKENS}) AS excerpt,
       bm25(chunks, {COLUMN_WEIGHTS})   AS score
FROM chunks LEFT JOIN videos ON videos.video_id = chunks.video_id
WHERE chunks MATCH ?
ORDER BY score, chunks.video_id, chunks.start_s
LIMIT ?
"""

TERM = re.compile(r'"[^"]*"?|\S+')
WORDISH = re.compile(r"\w", re.UNICODE)


class Unusable(RuntimeError):
    """The database on disk cannot answer queries as it stands."""


def db_path(home: Path) -> Path:
    return home / DB_NAME


def fts_query(text: str) -> str:
    """Turn user words into a MATCH expression that cannot be a syntax error.

    Every word becomes a phrase of its own, so punctuation a viewer would type
    ("C++", "don't", "--force") can never be read as query syntax; double-quoted
    groups stay phrases, and a trailing `*` still asks for a prefix match.
    """
    terms = []
    for raw in TERM.findall(text):
        quoted = raw.startswith('"')
        term = raw.strip('"') if quoted else raw
        suffix = ""
        if not quoted and term.endswith("*"):
            term, suffix = term[:-1], "*"
        if not WORDISH.search(term):
            continue
        terms.append('"' + term.replace('"', '""') + '"' + suffix)
    return " AND ".join(terms)


def _create(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except sqlite3.OperationalError as exc:
        db.close()
        if "fts5" in str(exc):
            raise Unusable(f"this SQLite has no FTS5 module — {exc}") from exc
        raise
    return db


def _open(path: Path) -> sqlite3.Connection | None:
    """Open an existing database this build understands, else None (rebuild it)."""
    if not path.is_file():
        return None
    db = None
    try:
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise sqlite3.DatabaseError("schema version")
        db.execute("SELECT video_id FROM chunks LIMIT 1").fetchone()
        db.execute("SELECT video_id FROM videos LIMIT 1").fetchone()
    except sqlite3.Error:
        if db is not None:
            db.close()
        return None
    return db


def _write_page(db: sqlite3.Connection, page: Page) -> None:
    _drop_video(db, page.video_id)
    db.execute(
        "INSERT INTO videos (video_id, title, channel, upload_date, url, duration_s)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (page.video_id, page.title, page.channel, page.upload_date, page.url, page.duration_s),
    )
    db.executemany(
        "INSERT INTO chunks (video_id, start_s, section, text) VALUES (?, ?, ?, ?)",
        [(page.video_id, s.start_s, s.title, s.text) for s in page.sections],
    )


def _drop_video(db: sqlite3.Connection, video_id: str) -> None:
    db.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))


def build(home: Path, pages) -> Path:
    """Rebuild the whole index from `pages`, replacing any database in place."""
    home.mkdir(parents=True, exist_ok=True)
    target = db_path(home)
    # Dotted temp name: a crashed build stays invisible and is never mistaken
    # for the index itself.
    tmp = home / f".{DB_NAME}.{os.getpid()}.tmp"
    tmp.unlink(missing_ok=True)
    try:
        with closing(_create(tmp)) as db, db:
            for page in pages:
                _write_page(db, page)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def replace_video(home: Path, video_id: str, page: Page | None) -> Path | None:
    """Refresh one video's rows in place; None when there is no index to update."""
    target = db_path(home)
    db = _open(target)
    if db is None:
        return None
    with closing(db), db:
        if page is None:
            _drop_video(db, video_id)
        else:
            _write_page(db, page)
    return target


def _result(row: sqlite3.Row) -> dict:
    start = int(row["start_s"] or 0)
    return {
        "video_id": row["video_id"],
        "title": row["title"] or row["video_id"],
        "section": row["section"] or "",
        "start_s": start,
        "timestamp": hms(start),
        "url": deep_link(row["video_id"], start),
        "excerpt": " ".join((row["excerpt"] or "").split()),
    }


def search(home: Path, query: str, limit: int) -> list[dict]:
    match = fts_query(query)
    if not match:
        return []
    db = _open(db_path(home))
    if db is None:
        raise Unusable(f"no usable index at {db_path(home)}")
    with closing(db):
        rows = db.execute(SEARCH_SQL, (match, limit)).fetchall()
    return [_result(row) for row in rows]
