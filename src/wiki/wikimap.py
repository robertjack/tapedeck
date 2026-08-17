"""SPEC-wiki-009: the maintainer is shown the wiki instead of made to find it.

SPEC-wiki-008 stopped tapedeck asking the agent to keep the catalog and the
chronology; this is the larger half of the same problem — tapedeck also stops
asking the agent to *discover* the wiki by reading it. Handed only `Read`, `Grep`
and `Glob`, a maintainer that is told "connect this to what is already here" has
no way to know which pages are worth opening, so it opens broadly and guesses.
Measured across ten real filings the number of *existing* notes each run rewrote
went 0, 0, 3, 2, 9, 12, 12, 13, 20, 15 — linear in the size of the wiki, against
notes averaging 20KB — and because an agent run re-reads its whole accumulated
context on every turn, a page opened early is paid for again on every turn after
it. A catalog line costs about 100 bytes against a note's 20KB; the map is the
same knowledge at roughly that ratio, so the saving compounds the same way the
waste did.

`render` is the map: one bounded line per page — everything but the three pinned
files, since a source page is as linkable as a note — built fresh from what is on
disk each time a run starts, never persisted, never a file of its own (adding one
to `wiki/` would put it under the gate, in the catalog, and in front of an
Obsidian reader that never asked for it). A wiki holding no such pages yields no
map at all, not an empty heading — an agent reads an empty section as a wiki whose
contents were withheld, which is worse than not raising the subject.

`shortlist` is the filing's own convenience beside the map: a short, ranked guess
at which of those pages share the video's vocabulary, computed here from the
words on the pages — not index's business, since `index` owns FTS5 retrieval over
*transcripts* and this is a throwaway ranking of wiki prose that exists nowhere
after the run ends. It is offered as a guess and worded as one, because the
ranking knows about shared words and nothing about shared ideas; the map beside
it stays complete so the pages a ranking passes over are still there to be found.
`tend` gets the map in both modes and no shortlist in either — it is about the
wiki entire and has no one video to rank against.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import layout

LINE_BUDGET = 160
SHORTLIST_SIZE = 3
WORD = re.compile(r"[a-z]{4,}")
MAP_HEADER = (
    "What this wiki already holds — one line per page, so you do not have to read "
    "the directory to find out what is here:"
)
SHORTLIST_HEADER = (
    "A guess, not a filter: these pages share the most vocabulary with this video, "
    "ranked, and are worth opening first — the rest of the map above is not "
    "off-limits, and the ranking knows nothing about shared ideas, only shared words:"
)
# Common English words a title, a transcript or an archive page's frontmatter
# scatters everywhere; excluded so a shared word means something.
STOPWORDS = frozenset(
    """
    that this with from have about into over under here more most some such very
    just also because been does done doing were will your then them than when
    what which while their there these those would could should being again
    after before during through until each other same both further having
    watch youtube com https www title channel upload date duration
    """.split()
)


def _catalogable(wiki: Path) -> list[Path]:
    """Every page the map owes a line to: everything but the three pinned files."""
    return [page for page in layout.pages(wiki) if not layout.is_pinned(wiki, page)]


def _line(wiki: Path, page: Path) -> str:
    where = layout.name(wiki, page)
    heading = " ".join((layout.opening_heading(layout.read(page)) or "").split())
    line = f"- {where}: {heading}" if heading else f"- {where}"
    if len(line) > LINE_BUDGET:
        line = line[: LINE_BUDGET - 1].rstrip() + "…"
    return line


def render(wiki: Path) -> str:
    """The map, or nothing when the wiki holds no linkable page yet."""
    pages = _catalogable(wiki)
    if not pages:
        return ""
    lines = "\n".join(_line(wiki, page) for page in pages)
    return f"{MAP_HEADER}\n\n{lines}"


def _words(text: str) -> Counter:
    return Counter(word for word in WORD.findall(text.lower()) if word not in STOPWORDS)


def shortlist(wiki: Path, subject_text: str, limit: int = SHORTLIST_SIZE) -> str:
    """A ranked guess at the pages whose vocabulary this video shares, or nothing
    when there is no candidate or no distinctive word to rank by."""
    query = _words(subject_text)
    if not query:
        return ""
    scored = []
    for page in _catalogable(wiki):
        overlap = _words(layout.read(page))
        score = sum(min(count, overlap[word]) for word, count in query.items() if word in overlap)
        if score > 0:
            scored.append((score, layout.name(wiki, page)))
    if not scored:
        return ""
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    listed = "\n".join(f"- {where}" for _, where in scored[:limit])
    return f"{SHORTLIST_HEADER}\n\n{listed}"
