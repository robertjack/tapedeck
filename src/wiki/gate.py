"""The acceptance gate, and the checks `lint` re-asks of a standing wiki.

The maintainer may write anything; this decides what lands (SPEC-wiki-002). Two
properties matter more than any individual check. It judges the **whole wiki**
rather than the diff, because a filing that fixes its own page while breaking a
link three notes away is exactly the failure worth catching. And every check is
independent and every failure is reported, because the maintainer gets one run
per operation and the user pays for each — a gate that reports one fault at a
time turns one rejection into several.

Each violation names the thing that broke it: the file that changed, the target
that dead-ends, the page the catalog forgot. A rejection nobody can act on costs
a maintainer run and buys nothing.

The individual checks are exported because `lint` asks the same questions of a
wiki nobody just wrote (SPEC-wiki-004). The gate is a moment and the wiki is a
life: what it accepts is sound the second it is committed, and nothing gates the
rename, the deletion or the reclaimed video that comes after.
"""

from __future__ import annotations

from pathlib import Path

from . import seams
from .layout import (
    BRIEF,
    ENTRY,
    INDEX,
    LOG,
    OPENS_LIKE_ENTRY,
    PAGE,
    PINNED,
    SOURCES,
    catalogued,
    cites,
    pages,
    rel,
    source_page,
    source_pages,
    targets,
    text_of,
)


def violations(
    home: Path, wiki: Path, video_id: str, brief_before: bytes | None, log_before: bytes
) -> list[str]:
    """Everything wrong with the wiki as the maintainer left it, all of it."""
    return [
        *_brief_kept(wiki, brief_before),
        *_filed(wiki, video_id),
        *(
            f"{page}: the wiki link to {target!r} resolves to no page in the wiki"
            for page, target in unresolved(wiki)
        ),
        *(f"{page}: {said}" for page, said in unverifiable(home, wiki)),
        *(
            f"{INDEX} does not link {page} — a page the catalog omits is a page "
            f"nobody opening this directory will find"
            for page in uncatalogued(wiki)
        ),
        *_chronology(wiki, log_before),
    ]


# --- the two checks that are about this operation ---


def _brief_kept(wiki: Path, before: bytes | None) -> list[str]:
    path = wiki / BRIEF
    if (path.read_bytes() if path.is_file() else None) == before:
        return []
    return [
        f"{BRIEF} was changed — the brief is the user's instructions to the "
        f"maintainer, and a maintainer that may rewrite its own instructions has "
        f"none, so any change at all fails the whole operation"
    ]


def _filed(wiki: Path, video_id: str) -> list[str]:
    path = source_page(wiki, video_id)
    name = f"{SOURCES}/{video_id}{PAGE}"
    if not path.is_file():
        return [
            f"{name} does not exist — that page is the whole record that "
            f"{video_id} has been filed"
        ]
    if not cites(text_of(path), video_id):
        return [
            f"{name} carries no deep link into {video_id} — a source page with no "
            f"anchor in its own recording is a summary of a memory rather than a "
            f"reading of it"
        ]
    return []


def _chronology(wiki: Path, before: bytes) -> list[str]:
    """Append-only as a byte-prefix, which is the only reading of it an agent
    cannot argue with, and then one new entry of the pinned shape."""
    path = wiki / LOG
    if not path.is_file():
        return [f"{LOG} is missing — the chronology is the wiki's record of itself"]
    now = path.read_bytes()
    if not now.startswith(before):
        return [
            f"{LOG} no longer begins with what it said before this run — the "
            f"chronology is append-only, and an entry that can be revised later is "
            f"not a record of what happened"
        ]
    if not ENTRY.search(now[len(before) :].decode("utf-8", "replace")):
        return [
            f"{LOG} gained no entry of the pinned shape "
            f"'## [YYYY-MM-DD] <op> | <subject>' — an accepted operation owes the "
            f"chronology a line, or the history has silent gaps"
        ]
    return []


# --- the checks that are about the wiki, whoever wrote it ---


def unresolved(wiki: Path) -> list[tuple[str, str]]:
    """Every wiki link that points at no page, as (page, target).

    The layout contract's rule and no other: the target is the text before the
    first `|`, matched case-sensitively against page basenames with `.md`
    stripped, satisfied by a page anywhere under `wiki/`. A dangling link is a
    page the writer believed existed, and it is the one defect nothing reading
    the wiki afterwards can route around.
    """
    known = {page.stem for page in pages(wiki)}
    return [
        (rel(wiki, page), target)
        for page in pages(wiki)
        for target in targets(text_of(page))
        if target not in known
    ]


def unverifiable(home: Path, wiki: Path) -> list[tuple[str, str]]:
    """Every page whose deep links ask cannot vouch for, as (page, what ask said).

    One page's text per invocation, so a verdict is always attributable to a
    page, and through ask's published verb so that the gate and the linter can
    never disagree about a link (LESSON-0003).
    """
    found = []
    for page in pages(wiki):
        said = seams.verify(home, text_of(page))
        if said is not None:
            found.append((rel(wiki, page), said))
    return found


def uncatalogued(wiki: Path) -> list[str]:
    """Pages the catalog does not mention. The three pinned files are not in it
    by rule; everything else must be, since `index.md` is how a reader learns
    what is in here."""
    index = wiki / INDEX
    listed = set(catalogued(text_of(index))) if index.is_file() else set()
    return [
        rel(wiki, page)
        for page in pages(wiki)
        if rel(wiki, page) not in PINNED and rel(wiki, page) not in listed
    ]


def dangling(wiki: Path) -> list[str]:
    """Catalog lines with nothing behind them — the failure a person produces by
    deleting or renaming a page and leaving the line describing it. The gate has
    no reason to check this and `lint` has every reason to."""
    index = wiki / INDEX
    if not index.is_file():
        return []
    return [
        target for target in catalogued(text_of(index)) if not (wiki / target).exists()
    ]


def unsourced(wiki: Path) -> list[str]:
    """Source pages that no longer cite their own video — prose survives edits
    that its citations do not."""
    return [page.stem for page in source_pages(wiki) if not cites(text_of(page), page.stem)]


def malformed(wiki: Path) -> list[str]:
    """Headings in the chronology that open like an entry and are not one. The
    shape is what keeps the log greppable without tooling."""
    log = wiki / LOG
    if not log.is_file():
        return []
    return [
        line for line in OPENS_LIKE_ENTRY.findall(text_of(log)) if not ENTRY.fullmatch(line)
    ]


def orphans(wiki: Path) -> list[str]:
    """Pages no other page links to. The catalog does not count as an incoming
    link: it links every page by rule, so counting it would mean no page is ever
    an orphan and the finding would never say anything."""
    linked: set[str] = set()
    for page in pages(wiki):
        if rel(wiki, page) != INDEX:
            linked.update(targets(text_of(page)))
    return [
        rel(wiki, page)
        for page in pages(wiki)
        if rel(wiki, page) not in PINNED and page.stem not in linked
    ]
