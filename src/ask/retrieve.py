"""Fast-mode retrieval: a question in, the top-k library chunks out.

The chunks live in `tapedeck.db`, which the index owns and rebuilds from archive
pages. ask only ever reads it — SPEC-core-001 gives ask write authority nowhere — so
the connection is opened read-only and cannot create, journal or touch a file by
accident.

We read it rather than shelling out to `index search` because the two retrievals are
not the same act. A searcher wants all their keywords, so `search` ANDs them; a
question is mostly grammar, and demanding "what", "is" and "the" alongside "core
idea" finds nothing. So ask drops the question words and ORs the rest — and it needs
whole section text, the channel a citation names, and a `--video` scope clause, none
of which crosses the search verb's surface.

Reading the file directly means inheriting the duty that came with it (SPEC-ask-004):
a database this build does not search under is not one ask may answer from, and it is
refused with the hint a missing database gets, before the answerer is invoked. The
shape is the index's to define, so `_shaped` asks the index what it is rather than
keeping a second copy of the answer — a copy that drifts is how `tapedeck search` and
`ask --fast` come to give two accounts of the same library.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from index.store import SCHEMA_VERSION, TOKENIZE

from .citations import deep_link, hms

DB_NAME = "tapedeck.db"
REINDEX_HINT = "run `tapedeck reindex`"

# Same weighting the index searches under: a hit in a section title beats one in
# prose, and the two unindexed columns still take a weight each.
COLUMN_WEIGHTS = "0.0, 0.0, 2.0, 1.0"  # video_id, start_s, section, text
SEARCH_SQL = f"""
SELECT chunks.video_id AS video_id, chunks.start_s AS start_s,
       chunks.section AS section, chunks.text AS text,
       COALESCE(videos.title, '') AS title, COALESCE(videos.channel, '') AS channel,
       bm25(chunks, {COLUMN_WEIGHTS}) AS score
FROM chunks LEFT JOIN videos ON videos.video_id = chunks.video_id
WHERE chunks MATCH ?"""
# `--video` narrows the retrieval itself, not its results: a scoped -k must buy k
# chunks of that video, not k of the library minus the ones that did not belong.
SCOPE_SQL = "\n  AND chunks.video_id = ?"
ORDER_SQL = "\nORDER BY score, chunks.video_id, chunks.start_s\nLIMIT ?\n"

TERM = re.compile(r'"[^"]*"?|\S+')
# A term the tokenizer can make a word of: at least one letter or digit. `\w` admits
# "___", which fts5 tokenizes to nothing and then refuses as an empty phrase.
ALNUM = re.compile(r"[^\W_]", re.UNICODE)
NOT_WORD = re.compile(r"\W+", re.UNICODE)

# The grammar a question is made of: ORed in, these drag in every chunk that has
# them, so they go unless dropping them leaves nothing. Only function words belong
# here — a word that could be what is being asked about stays in for bm25 to weigh.
STOPWORDS = frozenset(
    """
    a about after all also am an and any are as at be because been but by can could did
    do does doing for from had has have he her here him his how i if in into is it its
    just me more most my no not of on only or other our out over she should so some such
    than that the their them then there these they this those to too up us was we were
    what when where which while who why will with would you your
    """.split()
)

# A source is a passage to reason from, not a chapter to wade through: a longer
# section is cut at a word boundary, so eight of them stay a readable prompt.
EXCERPT_CHARS = 1600


class IndexUnreadable(RuntimeError):
    """The index cannot be read, so there is nothing to retrieve from."""


@dataclass(frozen=True)
class Source:
    """One retrieved chunk — what the prompt and the citation are both built from."""

    video_id: str
    title: str
    channel: str
    section: str
    start_s: int
    text: str

    @property
    def timestamp(self) -> str:
        return hms(self.start_s)

    @property
    def url(self) -> str:
        return deep_link(self.video_id, self.start_s)


def db_path(home: Path) -> Path:
    return home / DB_NAME


def terms(question: str) -> list[str]:
    """The question's searchable words: quoted groups whole, grammar dropped."""
    words: list[str] = []
    kept: list[str] = []
    for raw in TERM.findall(question):
        quoted = raw.startswith('"')
        term = raw.strip('"') if quoted else raw
        if not ALNUM.search(term):
            continue
        words.append(term)
        # A quoted group is the asker being deliberate — never second-guess it.
        if quoted or NOT_WORD.sub("", term.lower()) not in STOPWORDS:
            kept.append(term)
    return kept or words


def match_expression(question: str) -> str:
    """An fts5 MATCH the question cannot break and every word is optional in.

    Each word becomes a phrase of its own, so punctuation an asker types ("C++",
    "why?") is never read as query syntax, and the words are ORed: a chunk answering
    half the question is worth reading, and bm25 ranks fuller ones above it.
    """
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms(question))


def _shaped(db: sqlite3.Connection) -> bool:
    """Is this a database this build both understands and searches like?

    The version alone is not enough: rows stemmed by another tokenizer answer
    different queries under the same number, so the tokenizer is read off the
    database itself (SPEC-index-003, SPEC-ask-004).
    """
    if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        return False
    ddl = db.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks'").fetchone()
    return bool(ddl) and TOKENIZE in (ddl[0] or "")


def connect(home: Path) -> sqlite3.Connection:
    """A read-only handle on an index of the shape this build searches, or nothing."""
    path = db_path(home)
    if not path.is_file():
        raise IndexUnreadable(f"no index at {path} — {REINDEX_HINT}")
    db = None
    try:
        # Read-only URI: ask has no write authority over tapedeck.db — enforced
        # here rather than merely intended.
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        shaped = _shaped(db)  # a file that is no database at all fails here too
    except sqlite3.Error as exc:
        if db is not None:
            db.close()
        raise IndexUnreadable(f"cannot open {path} — {exc}; {REINDEX_HINT}") from exc
    if not shaped:
        db.close()
        raise IndexUnreadable(
            f"{path} was built by another schema or tokenizer — it is not an index "
            f"this build can search, so ask will not answer from it; {REINDEX_HINT}"
        )
    return db


def excerpt(text: str) -> str:
    text = text.strip()
    if len(text) <= EXCERPT_CHARS:
        return text
    head, sep, _ = text[:EXCERPT_CHARS].rpartition(" ")
    return f"{(head if sep else text[:EXCERPT_CHARS]).rstrip()} …"


def _source(row: sqlite3.Row) -> Source:
    return Source(
        video_id=row["video_id"],
        title=row["title"] or row["video_id"],
        channel=row["channel"] or "",
        section=row["section"] or "",
        start_s=int(row["start_s"] or 0),
        text=excerpt(row["text"] or ""),
    )


def top_k(home: Path, question: str, k: int, video_id: str | None = None) -> list[Source]:
    """The k chunks most worth answering from, best first; empty is an answer."""
    match = match_expression(question)
    db = connect(home)  # the shape is settled first, question or no question
    if not match:
        db.close()
        return []
    sql = SEARCH_SQL + (SCOPE_SQL if video_id else "") + ORDER_SQL
    params = [match, video_id, k] if video_id else [match, k]
    try:
        with closing(db):
            rows = db.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        raise IndexUnreadable(
            f"{db_path(home)} is not an index ask can read — {exc}; {REINDEX_HINT}"
        ) from exc
    return [_source(row) for row in rows]
