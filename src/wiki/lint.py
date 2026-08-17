"""`lint`: the gate's questions, asked of a wiki nobody just wrote.

The gate is a moment and the wiki is a life. Everything an operation accepts is
sound the second it is committed, and nothing gates what happens next: the user
renames a note in Obsidian, deletes a page they thought was redundant, edits a
source page's prose and takes its deep link with it, or reclaims a video with `rm`
and leaves the page that read it standing. Every one of those is legitimate — the
wiki is co-authored by design — and every one can leave it saying something that
is no longer true.

Read-only here is stricter than "writes no pages". No maintainer runs, no commit
is made, and in particular the pending `user edits` commit is not made either:
`file` commits because it is about to risk work a rollback must not take with it,
and a diagnosis risks nothing, so committing here would be a report quietly
changing the thing it was asked to describe. What is read is therefore the working
tree exactly as it stands — the wiki the user is actually looking at.

Every check is printed, the passes included, because a report that lists only
complaints cannot tell "checked and fine" from "never looked". Two of them only
ever report: a library that grew this morning is not a wiki that broke this
morning, and a note nothing points at yet is an ordinary moment in writing.

`unfiled` shares `library.eligible`'s selection walk with `sync` but passes it no
note callback (SPEC-wiki-010) — a diagnosis that only reads reports its findings
as check rows and says nothing about what it stepped over, so it never described a
staging directory in the first place and has nothing here to correct.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import gate, layout, library
from .filing import existing

PASS, FAIL, INFO = "pass", "fail", "info"
CHECKS = ("wikilinks", "citations", "index", "log", "sources", "filed", "unfiled", "orphans")
NAME_COLUMN = 11
STATUS_COLUMN = 6
SHOWN = 4


def _flat(text: str) -> str:
    return " ".join(str(text).split())


def _detail(problems: list[str], sound: str) -> tuple[str, str]:
    """A status and one line that names what decided it. A check that says only
    `fail` costs the user a second run to learn what everyone already knew."""
    if not problems:
        return PASS, sound
    shown = "; ".join(_flat(problem) for problem in problems[:SHOWN])
    extra = len(problems) - SHOWN
    return FAIL, shown + (f" (+{extra} more)" if extra > 0 else "")


def _named(paths: list[str], nothing: str, some: str) -> str:
    if not paths:
        return nothing
    listed = ", ".join(paths[:SHOWN])
    extra = len(paths) - SHOWN
    return f"{some.format(count=len(paths))}: {listed}" + (
        f" (+{extra} more)" if extra > 0 else ""
    )


def anchored(wiki: Path) -> list[str]:
    """The gate's rule about the page it just accepted, re-asked of every page ever
    accepted: prose survives edits that its citations do not."""
    return [
        f"{layout.name(wiki, page)} carries no deep link to {page.stem}"
        for page in layout.source_pages(wiki)
        if not layout.cites(layout.read(page), page.stem)
    ]


def reclaimed(home: Path, wiki: Path) -> list[str]:
    """Source pages whose video the library no longer holds. `rm` knows nothing
    about the wiki, by design — the wiki is not thrown away because the library
    shrank — but a page describing a video that is gone is knowledge left
    dangling, and what to do about it is the user's call. "Still in the library"
    means the entry, not the media: a video reclaimed by `rm --media-only` was
    explicitly kept as knowledge, and its page stands on the same footing."""
    return [
        f"{layout.name(wiki, page)}: {page.stem} is no longer in the library"
        for page in layout.source_pages(wiki)
        if not library.holds(home, page.stem)
    ]


def catalog_problems(wiki: Path, pages: list[Path]) -> list[str]:
    """The catalog in both directions. The gate checks only the first, and it is
    right to — the failure a maintainer produces is a page it forgot to catalog.
    The failure a person produces is the other one: they delete or rename a page
    and the line describing it stays behind, and `index.md` is read before
    anything else in the directory is."""
    return [
        f"{layout.INDEX} does not link {where}"
        for where in gate.uncatalogued(wiki, pages)
    ] + [
        f"{layout.INDEX} links {where}, and there is no such page"
        for where in gate.dangling(wiki)
    ]


def orphans(wiki: Path, pages: list[Path]) -> list[str]:
    """Pages no other page wikilinks to.

    The catalog does not count as an incoming link: `index.md` links every page by
    rule, so counting it would mean no page is ever an orphan and this line would
    report nothing at all. What it reports is where the wiki stopped being a web.
    """
    incoming: set[str] = set()
    for page in pages:
        if layout.name(wiki, page) == layout.INDEX:
            continue
        for target in layout.targets(layout.read(page)):
            if target != page.stem:
                incoming.add(target)
    return [
        layout.name(wiki, page)
        for page in pages
        if not layout.is_pinned(wiki, page) and page.stem not in incoming
    ]


def rows(home: Path, wiki: Path) -> list[dict]:
    pages = layout.pages(wiki)
    unfiled = [vid for vid in library.eligible(home) if not layout.filed(wiki, vid)]
    loose = orphans(wiki, pages)
    log = layout.read(wiki / layout.LOG)
    checked = [
        ("wikilinks", *_detail(
            gate.unresolved(wiki, pages),
            f"every wiki link in {len(pages)} page(s) resolves",
        )),
        ("citations", *_detail(
            gate.unverifiable(home, wiki, pages),
            f"every deep link in {len(pages)} page(s) verifies against the library",
        )),
        ("index", *_detail(
            catalog_problems(wiki, pages),
            "the catalog lists every page, and only pages that exist",
        )),
        ("log", *_detail(
            [f"malformed entry heading: {line}" for line in layout.malformed(log)],
            f"{len(layout.entries(log))} entry heading(s) match '{layout.ENTRY_SHAPE}'",
        )),
        ("sources", *_detail(
            anchored(wiki),
            f"all {len(layout.source_pages(wiki))} source page(s) cite their own video",
        )),
        ("filed", *_detail(
            reclaimed(home, wiki),
            "every source page's video is still in the library",
        )),
        ("unfiled", INFO, _named(
            unfiled,
            "every video eligible for filing has a page",
            "{count} eligible video(s) with no page — `tapedeck wiki sync` files them",
        )),
        ("orphans", INFO, _named(
            loose,
            "every page is linked from another page",
            "{count} page(s) no other page links to",
        )),
    ]
    return [{"check": name, "status": status, "detail": detail} for name, status, detail in checked]


def lint(home: Path, as_json: bool) -> int:
    """The report, in the pinned order, whatever each check found."""
    # The same wiki `file` resolves, and never a scaffolded one: a diagnosis that
    # creates what it was asked to diagnose has answered its own question.
    wiki = existing(home)
    report = rows(home, wiki)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for row in report:
            print(
                f"{row['check']:<{NAME_COLUMN}}{row['status']:<{STATUS_COLUMN}}{row['detail']}"
            )
    failed = [row["check"] for row in report if row["status"] == FAIL]
    if failed:
        print(f"{len(failed)} check(s) failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0
