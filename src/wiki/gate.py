"""The acceptance gate: what a maintainer wrote, judged as a whole wiki.

Probabilistic inside, deterministic at the edges (SPEC-wiki-002). The agent may write
anything; this decides what lands, and it decides it about the entire wiki rather than
about the diff — a filing that fixes its own page while breaking a link three notes
away is the failure this catches.

Each check is independent and every failure is reported. The maintainer gets one run
per operation and the user pays for each, so a gate that stops at the first fault turns
one rejection into several; and every violation names the thing that broke it — the
file that changed, the target that dead-ends, the page the catalog forgot — because a
rejection nobody can act on costs a run and buys nothing.

Two of the checks rest on vocabulary this component does not own. Whether a deep link
is *true* is ask's, asked through its published verb one page at a time. Whether a
page cites its own video is read with ask's own reading of a citation, imported rather
than rewritten: a second YouTube regex living here would be the defect whether or not
it currently agreed (LESSON-0003).
"""

from __future__ import annotations

import re
from pathlib import Path

from ask.citations import deep_links

from . import seams
from .scaffold import BRIEF, INDEX, LOG, PINNED, SOURCES

PAGE_SUFFIX = ".md"
GIT_DIR = ".git"

WIKILINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
MD_TARGET = re.compile(r"\]\(([^)\s]+)\)")
# The pinned chronology entry of contracts/wiki-layout.md.
ENTRY = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] \S+ \| .+$", re.MULTILINE)


def pages(wiki: Path) -> list[Path]:
    """Every markdown page in the wiki, git's own directory excepted. Anything that
    is not markdown is not a page: attachments are the user's business, and the
    catalog is not owed a line about them."""
    return sorted(
        path
        for path in wiki.rglob(f"*{PAGE_SUFFIX}")
        if path.is_file() and GIT_DIR not in path.relative_to(wiki).parts
    )


def snapshot(wiki: Path) -> dict[str, bytes | None]:
    """The two files judged against their pre-run selves. Taken once the user's edits
    are committed and before the maintainer runs, when the working tree and the
    pre-run commit are the same thing."""
    return {name: _bytes(wiki / name) for name in (BRIEF, LOG)}


def review(wiki: Path, home: Path, video_id: str, before: dict[str, bytes | None]) -> list[str]:
    """Everything wrong with this wiki, in the order a reader would want it."""
    found = pages(wiki)
    text: dict[Path, str] = {}
    problems: list[str] = []
    for page in found:
        try:
            text[page] = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{_rel(wiki, page)} cannot be read — {exc}")
    return (
        problems
        + _brief_untouched(wiki, before)
        + _filed(wiki, video_id, text)
        + _wikilinks(wiki, found, text)
        + _catalog(wiki, found, text)
        + _chronology(wiki, before)
        + _cited_truthfully(home, wiki, text)
    )


def _brief_untouched(wiki: Path, before: dict[str, bytes | None]) -> list[str]:
    """The brief is the user's instructions to the maintainer, and an agent that may
    rewrite its own instructions has none — any change at all, including one it
    believes is an improvement, fails the whole operation."""
    now = _bytes(wiki / BRIEF)
    if now == before[BRIEF]:
        return []
    verb = "deleted" if now is None else "restored" if before[BRIEF] is None else "edited"
    return [
        f"{BRIEF} was {verb} by the maintainer — the brief is the user's instructions, "
        f"and nothing in a filing may change a byte of it"
    ]


def _filed(wiki: Path, video_id: str, text: dict[Path, str]) -> list[str]:
    """The filed-state marker, and its anchor in the recording it describes."""
    page = wiki / SOURCES / f"{video_id}{PAGE_SUFFIX}"
    rel = f"{SOURCES}/{video_id}{PAGE_SUFFIX}"
    if page not in text:
        return [
            f"{rel} was not written — the sources page is the whole of what says "
            f"{video_id} has been filed"
        ]
    if any(link.video_id == video_id for link in deep_links(text[page])):
        return []
    return [
        f"{rel} carries no deep link to {video_id} itself — a source page with no "
        f"moment in its own recording is a summary of a memory, not a reading"
    ]


def _wikilinks(wiki: Path, found: list[Path], text: dict[Path, str]) -> list[str]:
    """Resolution is the whole rule of the layout contract: the text before the first
    `|`, matched case-sensitively against a page basename anywhere under the wiki."""
    known = {path.name[: -len(PAGE_SUFFIX)] for path in found}
    problems = []
    for page in found:
        for raw in WIKILINK.findall(text.get(page, "")):
            target = raw.split("|", 1)[0].strip()
            if target not in known:
                problems.append(
                    f"{_rel(wiki, page)} links to [[{target}]], which resolves to no "
                    f"page in the wiki"
                )
    return problems


def _catalog(wiki: Path, found: list[Path], text: dict[Path, str]) -> list[str]:
    """A page the catalog does not mention is a page nobody will find."""
    listed = {
        target.split("#", 1)[0].removeprefix("./")
        for target in MD_TARGET.findall(text.get(wiki / INDEX, ""))
    }
    return [
        f"{rel} is a stray page — nothing in {INDEX} links to it"
        for rel in (_rel(wiki, page) for page in found)
        if rel not in PINNED and rel not in listed
    ]


def _chronology(wiki: Path, before: dict[str, bytes | None]) -> list[str]:
    """Append-only as a byte-prefix, which is the only reading of it an agent cannot
    argue with, plus the entry this operation owes the record."""
    was = before[LOG] or b""
    now = _bytes(wiki / LOG) or b""
    if not now.startswith(was):
        return [
            f"{LOG} was rewritten — the chronology is append-only, and what it said "
            f"before an operation must still be how it begins, byte for byte"
        ]
    whole = now.decode("utf-8", "replace")
    boundary = len(was.decode("utf-8", "replace"))
    if any(match.start() >= boundary for match in ENTRY.finditer(whole)):
        return []
    return [
        f"{LOG} gained no entry of the pinned shape — an accepted operation owes the "
        f"chronology a line beginning '## [YYYY-MM-DD] <op> | <subject>'"
    ]


def _cited_truthfully(home: Path, wiki: Path, text: dict[Path, str]) -> list[str]:
    """Ask ask. Its verdict is the gate's verdict and its words are the ones reported;
    a message of our own here would be a second opinion on the same link."""
    problems = []
    for page, body in text.items():
        said = seams.ask_verify(home, body)
        if said:
            problems.append(f"{_rel(wiki, page)}: {said}")
    return problems


def _rel(wiki: Path, page: Path) -> str:
    return page.relative_to(wiki).as_posix()


def _bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None
