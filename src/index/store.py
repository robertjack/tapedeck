"""tapedeck.db: the database this component is the sole writer of.

Two properties do the work here.

*Disposable.* `build` writes a fresh database beside the old one and swaps it in,
so an interrupted rebuild leaves the previous index standing rather than a half
one (SPEC-core-003), and the file is never the only copy of anything: every row
comes from `archive/*.md` (SPEC-index-001).

*Self-describing.* The database says which schema laid it out (`PRAGMA
user_version`) and which tokenizer stemmed it (its own DDL), and `open_current`
refuses anything else — a foreign database is not read wrongly, it is not read at
all (SPEC-index-004). Only `build` is exempt, because rebuilding is the migration.

Ranking is bm25 with explicit tie-breaks, so insertion order — the one thing a
full rebuild and an incremental update do not share — never reaches the results.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .pages import Page, deep_link, hms

DB_NAME = "tapedeck.db"
SCHEMA_VERSION = 2
# Porter over unicode61, so morphological variants match (SPEC-index-003).
# Stemming happens at write time: a database built under another tokenizer answers
# different queries, which is why the DDL is checked alongside the version.
TOKENIZE = "porter unicode61 remove_diacritics 2"

SCHEMA = f"""
CREATE TABLE videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT '',
    upload_date TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    duration_s  INTEGER
);

-- One row per archive-page section (SPEC-index-001). The section title and its
-- prose are what searching matches; the id and start second ride along unindexed
-- so a hit can be addressed as a moment in a video.
CREATE VIRTUAL TABLE chunks USING fts5(
    video_id UNINDEXED,
    start_s UNINDEXED,
    section,
    text,
    tokenize = '{TOKENIZE}'
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
    """The database on disk is not one this build may read or write.

    `missing` separates the two cases a caller answers differently: nothing there
    yet (build it) from something there this build does not understand (refuse it).
    """

    def __init__(self, message, missing=False):
        super().__init__(message)
        self.missing = missing


def db_path(home: Path) -> Path:
    return home / DB_NAME


def fts_query(text: str) -> str:
    """User words as a MATCH expression that cannot be a syntax error.

    Every word becomes a phrase of its own, so punctuation a viewer would type
    ("C++", "don't", "--force") is never read as query syntax; a double-quoted
    group stays one phrase, and a trailing `*` still asks for a prefix match. The
    words are ANDed: a searcher who typed three of them meant all three. Phrases
    are stemmed on the way in, so quoting costs no morphology.
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
        # Stamped in the same breath as the schema it describes, so no database
        # this component writes is ever unlabelled (SPEC-index-004).
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except sqlite3.OperationalError as exc:
        db.close()
        if "fts5" in str(exc):
            raise Unusable(f"this SQLite has no FTS5 module — {exc}") from exc
        raise
    return db


def open_current(path: Path) -> sqlite3.Connection:
    """A handle on a database of exactly the shape this build writes, or nothing.

    The version alone would not be enough even if it were always bumped: rows
    stemmed by another tokenizer answer different queries under the same number,
    so the tokenizer is read off the database rather than assumed (SPEC-index-003).
    """
    if not path.is_file():
        raise Unusable(f"no index at {path}", missing=True)
    db = None
    try:
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise Unusable(
                f"{path} was written by schema version {version}, and this build "
                f"reads version {SCHEMA_VERSION}"
            )
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks'").fetchone()
        if not ddl or TOKENIZE not in (ddl[0] or ""):
            raise Unusable(f"{path} was stemmed by another tokenizer, not {TOKENIZE!r}")
    except sqlite3.Error as exc:
        if db is not None:
            db.close()
        raise Unusable(f"{path} cannot be read as an index — {exc}") from exc
    except Unusable:
        db.close()
        raise
    return db


def _drop_video(db: sqlite3.Connection, video_id: str) -> None:
    db.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))


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


def build(home: Path, pages) -> Path:
    """Rebuild the whole index from `pages`, replacing whatever is there."""
    home.mkdir(parents=True, exist_ok=True)
    target = db_path(home)
    # Dotted temp name: a crashed build stays invisible and is never mistaken for
    # the index itself.
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


def replace_video(home: Path, video_id: str, page: Page | None) -> Path:
    """Bring one video's rows in line with its page — or drop them (page None).

    The rows written are the rows `build` would have written for that page, which
    is what makes an updated database answer like a rebuilt one (SPEC-index-001).
    """
    target = db_path(home)
    with closing(open_current(target)) as db, db:
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
    """The `limit` best-matching chunks, best first. Empty is an answer."""
    # The database's shape is settled before the query is: a query with no words
    # left is nothing to run, but it is no reason to keep quiet about a database
    # this build cannot read (SPEC-index-004).
    with closing(open_current(db_path(home))) as db:
        match = fts_query(query)
        if not match:
            return []
        rows = db.execute(SEARCH_SQL, (match, limit)).fetchall()
    return [_result(row) for row in rows]
