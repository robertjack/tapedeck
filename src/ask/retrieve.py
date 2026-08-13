"""Fast-mode retrieval: a question in, the top-k library chunks out.

The chunks live in `tapedeck.db`, which the index owns and rebuilds from archive
pages alone. ask only ever reads it — SPEC-core-001 gives ask write authority
nowhere — so the connection is opened read-only and cannot create, journal or touch
a file even by accident. The schema is the index's, at the shape SPEC-index-001
pins; a database that has moved on is reported as unreadable rather than guessed at.

We read it rather than shelling out to `index search` because the two retrievals are
not the same act. A searcher types keywords and wants all of them, so `search` joins
the words with AND; a question is mostly grammar, and insisting that "what", "is" and
"the" appear alongside "core idea" finds nothing at all. So ask drops the question
words, ORs what is left and lets bm25 rank by overlap — and it needs each section's
whole text (a snippet is an excerpt to skim, not enough to answer from) and the
channel the citation line names, neither of which crosses the search verb's surface.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .citations import deep_link, hms

DB_NAME = "tapedeck.db"
REINDEX_HINT = "run `tapedeck reindex`"

# Same weighting the index searches under: a hit in a section title beats one in
# prose, and the two unindexed columns still take a weight each.
COLUMN_WEIGHTS = "0.0, 0.0, 2.0, 1.0"
SEARCH_SQL = f"""
SELECT chunks.video_id                    AS video_id,
       chunks.start_s                     AS start_s,
       chunks.section                     AS section,
       chunks.text                        AS text,
       COALESCE(videos.title, '')         AS title,
       COALESCE(videos.channel, '')       AS channel,
       bm25(chunks, {COLUMN_WEIGHTS})     AS score
FROM chunks LEFT JOIN videos ON videos.video_id = chunks.video_id
WHERE chunks MATCH ?
ORDER BY score, chunks.video_id, chunks.start_s
LIMIT ?
"""

TERM = re.compile(r'"[^"]*"?|\S+')
# A term the tokenizer can make a word of: at least one letter or digit. `\w` would
# not do — it admits "___", which fts5 tokenizes to nothing and then refuses as an
# empty phrase.
ALNUM = re.compile(r"[^\W_]", re.UNICODE)
NOT_WORD = re.compile(r"\W+", re.UNICODE)

# The grammar a question is made of: no retrieval signal, but they would drag in
# every chunk containing them, so they are dropped unless dropping them would leave
# nothing to search for. Only function words belong here — anything that could be
# what an asker is asking about ("way", "make", "one") stays in for bm25 to weigh.
STOPWORDS = frozenset(
    """
    a about after all also am an and any are as at be because been but by can could did
    do does doing for from had has have he her here him his how i if in into is it its
    just me more most my no not of on only or other our out over she should so some such
    than that the their them then there these they this those to too up us was we were
    what when where which while who why will with would you your
    """.split()
)

# One source is a passage to reason from, not a whole chapter to wade through: a
# section long enough to blow past this is cut at a word boundary, so eight of them
# stay a prompt an answerer can actually attend to.
EXCERPT_CHARS = 1600


class IndexUnreadable(RuntimeError):
    """The index cannot be read, so there is nothing to retrieve from."""


@dataclass(frozen=True)
class Source:
    """One retrieved chunk — what both the prompt and the citation are built from."""

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
    """The question's searchable words: quoted groups kept whole, grammar dropped."""
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
    "don't", "why?") is never read as query syntax, and the words are ORed: a chunk
    answering half the question is worth reading, and bm25 ranks fuller ones above it.
    """
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms(question))


def connect(home: Path) -> sqlite3.Connection:
    path = db_path(home)
    if not path.is_file():
        raise IndexUnreadable(f"no index at {path} — {REINDEX_HINT}")
    try:
        # Read-only URI: ask has no write authority over tapedeck.db, and this is the
        # enforcement rather than the intention.
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise IndexUnreadable(f"cannot open {path} — {exc}; {REINDEX_HINT}") from exc
    db.row_factory = sqlite3.Row
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


def top_k(home: Path, question: str, k: int) -> list[Source]:
    """The k chunks most worth answering from, best first. Empty is an answer."""
    match = match_expression(question)
    if not match:
        return []
    try:
        with closing(connect(home)) as db:
            rows = db.execute(SEARCH_SQL, (match, k)).fetchall()
    except sqlite3.Error as exc:
        raise IndexUnreadable(
            f"{db_path(home)} is not an index ask can read — {exc}; {REINDEX_HINT}"
        ) from exc
    return [_source(row) for row in rows]
