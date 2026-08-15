"""Reading the wiki as system/contracts/wiki-layout.md defines it.

Five paths are pinned and everything else about the wiki's shape belongs to the
brief, so the only things this module knows how to find are those five: the
brief, the catalog, the chronology, a source page and the notes tree. The rules
for reading them live here once because the acceptance gate (SPEC-wiki-002) and
`lint` (SPEC-wiki-004) ask the same questions of the same files — a linter that
disagreed with the gate about a link would be worse than no linter, since it
would send the user to fix a page the gate is perfectly happy with.

Two questions here are other components' and are consumed rather than re-derived
(LESSON-0003). Whether a directory name is a video id and whether its media is
present are ingest's, so `eligible` asks ingest. Whether a deep link is *true* —
where its URL ends when a full stop follows it, what an unknown duration waives —
is ask's, and is asked of `ask verify` in seams.py. What is read here is only
whether a page points at a given video at all, which is a question about the page
rather than about the link.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import ingest

# system/contracts/library-layout.md
DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY = "library"
ARCHIVE = "archive"
META_NAME = "meta.json"

# system/contracts/wiki-layout.md — the whole pinned tree
WIKI = "wiki"
BRIEF = "CLAUDE.md"
INDEX = "index.md"
LOG = "log.md"
SOURCES = "sources"
NOTES = "notes"
PINNED = (BRIEF, INDEX, LOG)
PAGE = ".md"

# `[[target]]` or `[[target|alias]]`: the target is the text before the first `|`.
WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
# An ordinary markdown link, which is how the catalog names a page.
MD_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
# The chronology's pinned heading, and anything that merely opens like one.
ENTRY = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] \S+ \| .+$", re.MULTILINE)
OPENS_LIKE_ENTRY = re.compile(r"^## \[.*$", re.MULTILINE)

# An upload_date that could not be read. Sorts after every real date, so a video
# whose metadata is illegible files last instead of never.
UNDATED = "~"


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def wiki_dir(home: Path) -> Path:
    return home / WIKI


def entry_of(home: Path, video_id: str) -> Path:
    return home / LIBRARY / video_id


def archive_page(home: Path, video_id: str) -> Path:
    return home / ARCHIVE / f"{video_id}{PAGE}"


def source_page(wiki: Path, video_id: str) -> Path:
    return wiki / SOURCES / f"{video_id}{PAGE}"


# --- the pages themselves ---


def pages(wiki: Path) -> list[Path]:
    """Every markdown page in the wiki, git's own directory excluded."""
    found = [
        path
        for path in wiki.rglob(f"*{PAGE}")
        if path.is_file() and ".git" not in path.relative_to(wiki).parts
    ]
    return sorted(found)


def source_pages(wiki: Path) -> list[Path]:
    directory = wiki / SOURCES
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(f"*{PAGE}") if path.is_file())


def rel(wiki: Path, page: Path) -> str:
    return page.relative_to(wiki).as_posix()


def text_of(page: Path) -> str:
    return page.read_text(encoding="utf-8", errors="replace")


def bytes_of(page: Path) -> bytes | None:
    return page.read_bytes() if page.is_file() else None


def targets(text: str) -> list[str]:
    """The wikilink targets a page offers, in order."""
    return [link.split("|", 1)[0].strip() for link in WIKILINK.findall(text)]


def catalogued(text: str) -> list[str]:
    """The wiki paths `index.md` links to, relative to the wiki root."""
    listed = []
    for target in MD_LINK.findall(text):
        if "://" in target or target.startswith("#"):
            continue  # an outward link is not a claim about a page in here
        cleaned = target.split("#", 1)[0].split("?", 1)[0].strip()
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if cleaned:
            listed.append(cleaned)
    return listed


def cites(text: str, video_id: str) -> bool:
    """Whether the text carries a deep link into this video, in the library
    layout's `watch?v=<id>&t=<seconds>s` shape. Whether that link is true is
    ask's question and is asked of ask; this one is about the page."""
    return bool(re.search(rf"watch\?v={re.escape(video_id)}&t=\d", text))


def today() -> str:
    return date.today().isoformat()


def append_entry(path: Path, op: str, subject: str, body: str) -> None:
    """Add one entry to the chronology, leaving every byte before it in place."""
    old = text_of(path) if path.is_file() else ""
    lead = "" if not old else ("\n" if old.endswith("\n") else "\n\n")
    path.write_text(
        f"{old}{lead}## [{today()}] {op} | {subject}\n\n{body}\n", encoding="utf-8"
    )


# --- what a sweep may file ---


def upload_date(entry: Path) -> str:
    """The date a sweep orders by. Metadata that cannot be read sorts last rather
    than stopping anything: the archive page is what a filing reads, and an
    illegible `meta.json` is no reason to leave a video out of the wiki forever."""
    try:
        meta = json.loads((entry / META_NAME).read_text(encoding="utf-8"))
        stamp = meta.get("upload_date") if isinstance(meta, dict) else None
    except (OSError, ValueError):
        return UNDATED
    return stamp if isinstance(stamp, str) and stamp else UNDATED


def eligible(home: Path, note=None) -> tuple[list[str], int]:
    """The library entries a sweep could file, in `upload_date` order with ties
    broken by id, and the count of what it had to pass over.

    The three preconditions are `file`'s own, hoisted to the front so the sweep
    never starts an operation it knows will fail (SPEC-wiki-003). Everything else
    under `library/` is a permanent resident of a real library — a directory of
    the user's own, an entry whose media `rm --media-only` reclaimed, one archive
    has not rendered yet — and a sweep that failed on those could never converge.
    """
    library = home / LIBRARY
    ready: list[tuple[str, str]] = []
    skipped = 0
    for entry in sorted(library.iterdir()) if library.is_dir() else []:
        if not entry.is_dir():
            continue
        video_id = entry.name
        if not ingest.VIDEO_ID.fullmatch(video_id):
            reason = "not a video id — skipped, it is not tapedeck's"
        elif not ingest.has_video(entry):
            reason = (
                "no video file — skipped; its media was reclaimed and the wiki "
                "files from the library, not from a gap in it"
            )
        elif not archive_page(home, video_id).is_file():
            reason = (
                f"no archive page — skipped; the maintainer reads that page, so "
                f"`tapedeck add {video_id}` has to render it first"
            )
        else:
            ready.append((upload_date(entry), video_id))
            continue
        skipped += 1
        if note is not None:
            note(f"{video_id}: {reason}")
    return [video_id for _, video_id in sorted(ready)], skipped
