"""The acceptance gate: what a maintainer's work has to survive to be committed.

tapedeck does not review the agent's prose, its taxonomy, or its judgment about
what deserves a note. It reviews the result, and it reviews the **whole wiki**
rather than the diff — a maintainer edits wherever the brief sends it, and a
filing that fixes its own page while breaking a link three notes away is exactly
the failure this catches.

Every check is independent and every failure is reported. One rejected run costs a
maintainer invocation, and a gate that stopped at the first violation would turn
one rejection into several. Every violation names the thing that broke it — the
file that changed, the target that dead-ends, the page the catalog forgot —
because a rejection nobody can act on buys nothing.

Three of the checks are about a before and an after, and what they compare against
is read off the disk before the agent runs rather than out of git afterwards: the
question is what the file said, not what a checkout of it would say.

The individual checks are exported because `lint` re-asks them of a wiki nobody
just wrote (SPEC-wiki-004), and because the two must never disagree — a linter
that sent the user to fix a page the gate is perfectly happy with would be worse
than no linter. The one thing neither of them re-derives is citation grammar:
pages go to ask's published `verify`, one page's text per invocation, and what ask
says about a bad link is what reaches the user (LESSON-0003). Wikilink resolution
reads code spans the way `layout.targets` does (SPEC-wiki-011), so a page that
quotes the `[[syntax]]` in backticks is never mistaken for a page that broke it.

The catalog and the chronology are checked here exactly as they always were
(SPEC-wiki-008): every page linked from `index.md`, `log.md` grown by a
well-formed entry. What changed is not this module but what runs before it —
tapedeck's own bookkeeping reconciles both after the maintainer exits and before
`verdict` is asked anything, so these two checks are now invariants satisfied by
construction rather than obligations an agent can fail.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from . import layout, seams


class Before(NamedTuple):
    """What the wiki said when the operation began."""

    brief: bytes | None
    log: bytes
    sources: frozenset[str]


def snapshot(wiki: Path) -> Before:
    """Taken after the `user edits` commit and before the agent runs, so what the
    gate compares against is the state the rollback would return to."""
    brief = wiki / layout.BRIEF
    log = wiki / layout.LOG
    return Before(
        brief=brief.read_bytes() if brief.is_file() else None,
        log=log.read_bytes() if log.is_file() else b"",
        sources=frozenset(
            layout.name(wiki, page) for page in layout.source_pages(wiki)
        ),
    )


def brief_kept(wiki: Path, before: Before) -> list[str]:
    """The user's instructions to the maintainer, byte for byte.

    An agent that may rewrite its own instructions has none — it has a draft — so
    any change at all fails, including one the maintainer believes is an
    improvement.
    """
    path = wiki / layout.BRIEF
    now = path.read_bytes() if path.is_file() else None
    if now == before.brief:
        return []
    return [
        f"{layout.BRIEF} was changed — the brief is the user's instructions to the "
        f"maintainer, and an agent that may rewrite its own instructions has none"
    ]


def marker_written(wiki: Path, video_id: str, url: str) -> list[str]:
    """The filing's own claim: the page exists, and it is anchored in the
    recording it describes rather than being a summary of a memory."""
    page = layout.source_page(wiki, video_id)
    where = layout.name(wiki, page)
    if not page.is_file():
        return [
            f"{where} does not exist — that page is the whole record that "
            f"{video_id} has been filed"
        ]
    if not layout.cites(layout.read(page), url):
        return [
            f"{where} carries no deep link into {video_id} itself — a source page "
            f"with no anchor in its own recording is a summary of a memory"
        ]
    return []


def sources_kept(wiki: Path, before: Before) -> list[str]:
    """No page under `sources/` deleted or renamed away.

    Filed-state is not bookkeeping the wiki keeps beside its content: the page's
    existence is the answer to "has this video been filed", and `sync` has no
    other. A tidy-up that folded one away would un-file a video silently, the next
    sweep would spend a maintainer run recreating what a maintainer had just
    decided to remove, and nothing in the wiki would be wrong enough for any other
    check to say so.
    """
    return [
        f"{where} was deleted or renamed away — that page's existence is what "
        f"records its video as filed, and removing it un-files that video silently"
        for where in sorted(before.sources)
        if not (wiki / where).is_file()
    ]


def unresolved(wiki: Path, pages: list[Path]) -> list[str]:
    """Every wikilink that points at no page.

    The layout contract's rule and no other: the text before the first `|`,
    matched case-sensitively against page basenames with `.md` stripped, satisfied
    by a page anywhere under `wiki/`, and never a link at all inside a code span
    or a fenced block (SPEC-wiki-011). A dangling link is a page the writer
    believed existed, and it is the one defect nothing reading the wiki afterwards
    can route around.
    """
    known = layout.resolvable(pages)
    return [
        f"{layout.name(wiki, page)}: the wiki link [[{target}]] resolves to no page"
        for page in pages
        for target in layout.targets(layout.read(page))
        if target not in known
    ]


def unverifiable(home: Path, wiki: Path, pages: list[Path]) -> list[str]:
    """Every page whose deep links ask cannot vouch for, in ask's own words."""
    found = []
    for page in pages:
        said = seams.unverifiable(home, layout.read(page))
        if said is not None:
            found.append(f"{layout.name(wiki, page)}: {said}")
    return found


def uncatalogued(wiki: Path, pages: list[Path]) -> list[str]:
    """Pages the catalog does not mention. The three pinned files are outside it
    by rule; everything else must be in it, since `index.md` is how a reader
    learns what is here and a page it omits is a page nobody will find."""
    listed = set(layout.catalog(layout.read(wiki / layout.INDEX)))
    return [
        layout.name(wiki, page)
        for page in pages
        if layout.name(wiki, page) not in layout.PINNED
        and layout.name(wiki, page) not in listed
    ]


def dangling(wiki: Path) -> list[str]:
    """Catalog lines with nothing behind them — the failure a person produces by
    deleting or renaming a page and leaving the line describing it. The gate has
    no reason to check this and `lint` has every reason to."""
    return [
        target
        for target in layout.catalog(layout.read(wiki / layout.INDEX))
        if not (wiki / target).is_file()
    ]


def chronology(wiki: Path, before: Before) -> list[str]:
    """Append-only as a byte-prefix — the only reading of it an agent cannot argue
    with — and then one new entry of the pinned shape, since an accepted operation
    that recorded nothing leaves a silent gap in the wiki's account of itself."""
    path = wiki / layout.LOG
    if not path.is_file():
        return [f"{layout.LOG} is missing — the chronology is the wiki's own record"]
    now = path.read_bytes()
    if not now.startswith(before.log):
        return [
            f"{layout.LOG} no longer begins with what it said before this run — the "
            f"chronology is append-only, and an entry that can be revised later is "
            f"not a record of what happened"
        ]
    fresh = now[len(before.log) :].decode("utf-8", errors="replace")
    if not layout.entries(fresh):
        return [
            f"{layout.LOG} gained no entry of the pinned shape "
            f"'{layout.ENTRY_SHAPE}' — an accepted operation owes the chronology a "
            f"line, or the history has silent gaps"
        ]
    return []


def verdict(
    home: Path,
    wiki: Path,
    before: Before,
    video_id: str | None = None,
    url: str = "",
    keep_sources: bool = False,
) -> list[str]:
    """Everything wrong with the wiki as the agent left it, all of it.

    `video_id` asks the filing's own question — that this video's marker appeared,
    anchored via `url`, the video's own address (SPEC-ingest-005). `keep_sources`
    asks the same concern the other way round, and is what stands in its place on
    a run that files no video: that no marker disappeared.
    """
    pages = layout.pages(wiki)
    problems = brief_kept(wiki, before)
    if video_id is not None:
        problems += marker_written(wiki, video_id, url)
    if keep_sources:
        problems += sources_kept(wiki, before)
    problems += unresolved(wiki, pages)
    problems += unverifiable(home, wiki, pages)
    problems += [
        f"{layout.INDEX} does not link {where} — a page the catalog omits is a page "
        f"nobody opening this directory will find"
        for where in uncatalogued(wiki, pages)
    ]
    problems += chronology(wiki, before)
    return problems
