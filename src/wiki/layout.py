"""The wiki's shape: the five pinned paths, and the three grammars over them.

This module is system/contracts/wiki-layout.md written down once. Everything the
gate and the linter check mechanically is asked here — where a page lives, what a
`[[wikilink]]` points at, what the catalog links, what a chronology entry looks
like — so the two of them can never disagree about what the contract says.

What is deliberately absent is as load-bearing as what is here. There is no
YouTube-link parser: whether a deep link is real is ask's vocabulary and is
consumed through ask's published `verify` boundary (LESSON-0003), and the one
question this module answers about a link is whether a page mentions the deep-link
form of a given video at all — the library layout's own format, not a second
reading of it. There is no page template, no taxonomy and no naming rule either:
those live in `CLAUDE.md`, which is the user's, and a clause about them here would
be specifying how someone else is allowed to think.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

WIKI = "wiki"
SOURCES = "sources"
NOTES = "notes"
BRIEF = "CLAUDE.md"
INDEX = "index.md"
LOG = "log.md"
# The three files the catalog does not list and the orphan check does not judge.
PINNED = (BRIEF, INDEX, LOG)
TREES = (SOURCES, NOTES)
PAGE = ".md"
GIT = ".git"

# `[[target]]` or `[[target|alias]]`: the target is the text before the first `|`,
# matched case-sensitively against page basenames with `.md` stripped.
WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
# The catalog's line: an ordinary markdown link whose target is a page's path
# relative to the wiki root.
MARKDOWN_LINK = re.compile(r"\]\(\s*([^()\s]+)\s*\)")
# The chronology's entry, fixed so the log stays greppable without tooling.
ENTRY = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] (\S+) \| (.+)$")
ENTRY_OPENS = "## ["
ENTRY_SHAPE = "## [YYYY-MM-DD] <op> | <subject>"


def wiki_dir(home: Path) -> Path:
    """`$TAPEDECK_HOME/wiki` — beside `library/` and `archive/`, its own git repo."""
    return home / WIKI


def source_page(wiki: Path, video_id: str) -> Path:
    """One page per filed video. Its existence is the filed-state marker: there is
    no manifest to keep in step, so `ls sources/` is the answer to what is filed."""
    return wiki / SOURCES / f"{video_id}{PAGE}"


def filed(wiki: Path, video_id: str) -> bool:
    return source_page(wiki, video_id).is_file()


def pages(wiki: Path) -> list[Path]:
    """Every markdown page in the wiki, in a stable order. The git directory is
    not the wiki: nothing under it is a page and nothing there is ever judged."""
    found = [
        path
        for path in wiki.rglob(f"*{PAGE}")
        if path.is_file() and GIT not in path.relative_to(wiki).parts
    ]
    return sorted(found)


def source_pages(wiki: Path) -> list[Path]:
    """Every filed video's page — `ls sources/` is the answer to what is filed."""
    tree = wiki / SOURCES
    return sorted(page for page in tree.glob(f"*{PAGE}") if page.is_file())


def name(wiki: Path, page: Path) -> str:
    """A page as the catalog and every message names it: `notes/thing.md`."""
    return page.relative_to(wiki).as_posix()


def is_pinned(wiki: Path, page: Path) -> bool:
    return name(wiki, page) in PINNED


def read(page: Path) -> str:
    """A page's text, never an exception. Undecodable bytes are replaced rather
    than swallowed: a page tapedeck cannot read cleanly still has links in it, and
    silently reading it as empty would wave every one of them through."""
    try:
        return page.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def targets(text: str) -> list[str]:
    """The wikilink targets in a page, in order, aliases stripped."""
    return [link.split("|", 1)[0].strip() for link in WIKILINK.findall(text)]


def resolvable(pages: list[Path]) -> set[str]:
    """What a wikilink may resolve to: any page's basename with `.md` stripped,
    from any depth. No paths, no extensions, no fuzzy or nearest-match."""
    return {page.stem for page in pages}


def catalog(index_text: str) -> list[str]:
    """The wiki pages `index.md` links to, as paths relative to the wiki root.

    Only markdown links naming a `.md` file count: the brief decides everything
    else about a catalog line — grouping, ordering, whether the trailing dash
    carries a summary — and an outbound URL in an annotation is not a claim that
    the wiki contains a page.
    """
    found = []
    for target in MARKDOWN_LINK.findall(index_text):
        if "://" in target:
            continue
        path = target.split("#", 1)[0].strip().removeprefix("./")
        if path.endswith(PAGE):
            found.append(path)
    return found


def entries(log_text: str) -> list[tuple[str, str]]:
    """The chronology as `(op, subject)` pairs, oldest first."""
    found = []
    for line in log_text.splitlines():
        match = ENTRY.match(line)
        if match:
            found.append((match.group(1), match.group(2)))
    return found


def malformed(log_text: str) -> list[str]:
    """Lines that open like an entry and are not one. The heading shape is what
    keeps the log readable by `grep`, so a heading that drifted out of it is an
    event the chronology can no longer be read to contain."""
    return [
        line.rstrip()
        for line in log_text.splitlines()
        if line.startswith(ENTRY_OPENS) and not ENTRY.match(line)
    ]


def deep_link_form(video_id: str) -> str:
    """How a moment in this video is addressed, in the library layout's one
    format — quoted to the maintainer so it never has to invent the shape."""
    return f"https://www.youtube.com/watch?v={video_id}&t=<seconds>s"


def cites(text: str, video_id: str) -> bool:
    """Does this page anchor itself in this recording?

    Deliberately the narrowest possible question: whether the layout's deep-link
    form for *this* id appears at all. Whether the links a page carries are true
    is decided by ask and by nothing here, so this never has to know where a URL
    ends or what an unknown duration waives.
    """
    return f"watch?v={video_id}" in text


def today() -> str:
    return date.today().isoformat()


# The brief is a page like any other, and the gate reads every page: a wiki link
# written out here would have to resolve, and a YouTube URL written out here would
# be read as a citation and checked against the library. So this text describes
# both forms rather than spelling either one — which is also the warning the file
# gives its reader.
DEFAULT_BRIEF = """# The maintainer's brief

You are the maintainer of this wiki: the prose side of a tapedeck library — what
the videos said, and what was made of it. tapedeck wrote this file once and will
never write it again. It is the user's. Rewriting it wholesale is the intended end
state, not a fault.

## The layout

    CLAUDE.md           this brief — never edited by the maintainer
    index.md            the catalog: one markdown-linked line per page
    log.md              the chronology, append-only
    sources/<id>.md     one page per filed video; its existence is the filed marker
    notes/              free-form pages; how they are organized is this file's business

Everything is plain markdown, so the directory opens as an Obsidian vault with no
conversion and reads fine in `grep`. Pages point at each other with a wiki link:
a page's filename without `.md`, wrapped in doubled square brackets, with a
display alias after a `|` if you want one. Every accepted operation is a git
commit, so a filing you dislike is one `git revert` away.

A moment in a video is addressed by its ordinary YouTube watch URL, carrying the
video id and a `t=` offset in seconds. The archive page you file from already
carries one in every section heading — copy them from there, and never
reconstruct one from memory.

## What tapedeck checks after every operation

An operation that breaks any of these is rejected whole and its work is discarded:

- This file is byte-identical to how the operation found it.
- `sources/<id>.md` exists for the video being filed and carries at least one deep
  link into that video.
- Every wiki link resolves — case-sensitively, against page filenames with `.md`
  stripped, satisfied by a page anywhere under `wiki/`.
- Every deep link anywhere in the wiki names a real video in this library at a
  moment inside it. In this file too: a URL written out here in full would be read
  as a claim and checked as one, which is why there is not one on this page.
- `index.md` links every page except the three above.
- `log.md` still begins with exactly what it said before and has gained an entry
  of the form `## [YYYY-MM-DD] <op> | <subject>`.

Nothing above says what a page should contain. That is what the rest of this file
is for.

## Conventions — replace these with your own

- A source page opens with the title and channel, then what the video actually
  argues, in your words, with a deep link at every claim worth returning to.
- A claim earns its own note when a second video has made it. Name notes for the
  idea, lower-case and hyphenated: `notes/cache-invalidation.md`.
- Prefer linking to repeating. When a page starts explaining something another
  page owns, link that page instead.
- Say what you doubt. A note that records the objection is worth more later than
  one that only records the claim.
- Write for the reader you will be in a year, who remembers none of this.
"""
