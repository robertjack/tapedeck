"""`lint` — doctor's sibling one layer up: is what the work produced still true?

Where `doctor` says whether this installation can do the work (SPEC-cli-007),
`lint` says whether the wiki still holds together (SPEC-wiki-004). It exists
because the gate is a moment and the wiki is a life: everything the gate accepts
is sound the second it is committed, and nothing gates the note renamed in
Obsidian, the page deleted as redundant, the prose edited out from around its
deep link, or the video reclaimed by `rm` under a page that still reads it. Every
one of those is legitimate — the wiki is co-authored by design — and every one
can leave the wiki saying something that is no longer true.

Every check is printed, the passes included, because a report that lists only
complaints cannot tell "checked and fine" from "never looked". The two checks
that only ever report carry `info`: a count of nothing is still information
rather than a thing that passed, and neither ever touches the exit code, so a
wiki that is sound but incomplete is sound.

Read-only is the whole discipline and it is stricter than "writes no pages". No
maintainer runs, no commit is made, and pending hand-edits are left pending —
`file` commits those because it is about to risk work a rollback must not take
with it, and a diagnosis that risks nothing has nothing to protect. So what is
read is the working tree exactly as it stands, which is the wiki the user is
actually looking at.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import Usage, gate
from .filing import unfiled
from .layout import (
    ENTRY,
    LOG,
    PINNED,
    eligible,
    entry_of,
    pages,
    rel,
    source_pages,
    targets,
    text_of,
    wiki_dir,
)

PASS, FAIL, INFO = "pass", "fail", "info"
# SPEC-wiki-004 pins these and their order; every one is emitted every run.
CHECKS = ("wikilinks", "citations", "index", "log", "sources", "filed", "unfiled", "orphans")
# How many named things a detail carries before it starts counting instead.
SHOWN = 6


def row(check: str, status: str, detail: str) -> dict:
    # Collapsed to one line on purpose: the report is a column a person skims,
    # and a detail that wrapped would stop it being one.
    return {"check": check, "status": status, "detail": " ".join(detail.split())}


def listed(items: list[str]) -> str:
    shown = "; ".join(items[:SHOWN])
    return shown if len(items) <= SHOWN else f"{shown} (+{len(items) - SHOWN} more)"


def diagnose(home: Path, wiki: Path) -> list[dict]:
    """The eight checks, in the pinned order, whatever each of them found."""
    every = pages(wiki)
    # The three pinned files are not catalogued and are not orphans; everything
    # else in here is a page the catalog owes a line to.
    content = [page for page in every if rel(wiki, page) not in PINNED]
    sources = source_pages(wiki)

    broken = gate.unresolved(wiki)
    links = sum(len(targets(text_of(page))) for page in every)
    rows = [
        row(
            "wikilinks",
            FAIL if broken else PASS,
            listed([f"{page} points at {target!r}" for page, target in broken])
            if broken
            else f"{links} link(s) resolve"
            if links
            else "no wiki links to resolve yet",
        )
    ]

    unverified = gate.unverifiable(home, wiki)
    rows.append(
        row(
            "citations",
            FAIL if unverified else PASS,
            listed([f"{page}: {said}" for page, said in unverified])
            if unverified
            else f"ask verified the deep links in {len(every)} page(s)",
        )
    )

    missing = [f"{page} is not in the catalog" for page in gate.uncatalogued(wiki)]
    ghosts = [f"{target} is catalogued but not in the wiki" for target in gate.dangling(wiki)]
    catalog = missing + ghosts
    rows.append(
        row(
            "index",
            FAIL if catalog else PASS,
            listed(catalog)
            if catalog
            else f"{len(content)} page(s) catalogued, every line resolves",
        )
    )

    headings = gate.malformed(wiki)
    entries = len(ENTRY.findall(text_of(wiki / LOG))) if (wiki / LOG).is_file() else 0
    rows.append(
        row(
            "log",
            FAIL if headings else PASS,
            listed(headings)
            if headings
            else f"{entries} entr(ies), every heading well-formed"
            if entries
            else "no entries yet",
        )
    )

    unanchored = gate.unsourced(wiki)
    rows.append(
        row(
            "sources",
            FAIL if unanchored else PASS,
            listed([f"{video_id} cites no moment in its own video" for video_id in unanchored])
            if unanchored
            else f"{len(sources)} source page(s) cite their own video"
            if sources
            else "no videos filed yet",
        )
    )

    gone = [page.stem for page in sources if not entry_of(home, page.stem).is_dir()]
    rows.append(
        row(
            "filed",
            FAIL if gone else PASS,
            listed([f"{video_id} is filed here but no longer in the library" for video_id in gone])
            if gone
            else f"every filed video is still in the library ({len(sources)})",
        )
    )

    # Eligibility is the sweep's, and the skips it would report are not this
    # report's business: what is worth saying is which videos are waiting.
    ready, _ = eligible(home)
    waiting = unfiled(wiki, ready)
    rows.append(
        row(
            "unfiled",
            INFO,
            f"{len(waiting)} eligible video(s) not filed yet — `sync` files them: "
            + listed(waiting)
            if waiting
            else "none — every eligible video in the library is filed",
        )
    )

    alone = gate.orphans(wiki)
    rows.append(
        row(
            "orphans",
            INFO,
            f"{len(alone)} page(s) nothing links to: " + listed(alone)
            if alone
            else "none — every page has an incoming wiki link",
        )
    )
    # The order is pinned surface, not the order these happened to be written in.
    found = {item["check"]: item for item in rows}
    return [found[name] for name in CHECKS]


def report(rows: list[dict]) -> str:
    """One aligned line per check, so the statuses skim as a column."""
    width = max(len(item["check"]) for item in rows)
    status = max(len(item["status"]) for item in rows)
    return "\n".join(
        f"{item['check']:<{width}}  {item['status']:<{status}}  {item['detail']}"
        for item in rows
    )


def run(home: Path, as_json: bool) -> int:
    wiki = wiki_dir(home)
    if not wiki.is_dir():
        # A diagnosis that scaffolds what it was asked to diagnose has answered
        # its own question with its own handiwork.
        raise Usage(
            f"no wiki at {wiki} to check — `python -m wiki file <id>` or "
            f"`python -m wiki sync` makes one; lint only reads"
        )
    rows = diagnose(home, wiki)
    # No escape sequences, ever: this is read by pipes and by `--json` consumers
    # as often as by people.
    print(json.dumps(rows, ensure_ascii=False, indent=2) if as_json else report(rows))
    broken = [item["check"] for item in rows if item["status"] == FAIL]
    if broken:
        print(f"{len(broken)} check(s) failed: {', '.join(broken)}", file=sys.stderr)
    return 1 if broken else 0
