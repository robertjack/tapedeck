"""What first use puts in `$TAPEDECK_HOME/wiki/`, once, and never again.

The five pinned entries of system/contracts/wiki-layout.md and nothing else: the two
directories, a default brief, an empty catalog and an empty chronology. Nothing here
ever overwrites a file that is already on disk — the brief in particular is scaffolded
exactly as config.toml is (SPEC-core-004, SPEC-wiki-001): tapedeck writes a default so
there is something to read and edit on the first day, and from then on the file is the
user's, never rewritten and never migrated. A brief the user has replaced wholesale is
the intended end state, not a fault condition.

The default brief carries no wikilink and no deep link of its own, on purpose. It is a
page like any other to the gate that reads it, and an example link in a file nobody
means as content would fail every filing until someone deleted it.
"""

from __future__ import annotations

from pathlib import Path

BRIEF = "CLAUDE.md"
INDEX = "index.md"
LOG = "log.md"
PINNED = (BRIEF, INDEX, LOG)
SOURCES = "sources"
NOTES = "notes"


def ensure(wiki: Path) -> bool:
    """Make the wiki usable, creating only what is missing. Returns whether this call
    is the one that brought it into existence — the caller names the first commit."""
    fresh = not wiki.exists()
    for directory in (wiki, wiki / SOURCES, wiki / NOTES):
        directory.mkdir(parents=True, exist_ok=True)
    _create(wiki / BRIEF, BRIEF_TEXT)
    _create(wiki / INDEX, "")
    _create(wiki / LOG, "")
    return fresh


def _create(path: Path, text: str) -> None:
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        pass


BRIEF_TEXT = """\
# The tapedeck wiki

This is a companion to a library of transcribed videos. The library is one directory
up: `archive/<id>.md` is a readable page per video — frontmatter, then a section per
chapter, each heading timestamped and linked into the recording itself — and
`library/<id>/` holds the metadata and the transcript behind it.

The wiki is what someone made of all that: the connections, the naming, the second
thought a month later. It accumulates one filing at a time and it is never regenerated
from the library, so nothing written here has to be re-derivable from anything.

## The shape of it

- `CLAUDE.md` — this file. The conventions below are the maintainer's instructions.
- `index.md` — the catalog. One markdown-linked line per page in the wiki.
- `log.md` — the chronology. One entry per accepted operation, newest at the bottom.
- `sources/<video-id>.md` — one page per filed video. Its existence is what says the
  video has been filed; there is no list anywhere else to keep in step with it.
- `notes/` — everything else. Ideas, people, questions, threads across videos.

## What tapedeck checks, and rejects the whole filing over

These are mechanical. A run that breaks one of them is thrown away entire, so the
wiki is never left half-written.

1. `sources/<id>.md` exists for the video being filed, and carries at least one deep
   link to that same video — the `watch?v=<id>&t=<seconds>s` form the archive page
   already uses. Take ids and offsets off the page you read; never reconstruct one
   from memory.
2. Every deep link anywhere in the wiki points at a video the library really holds,
   at a moment inside its real length. A note that cites nothing is fine; a note that
   cites something false is not.
3. Every wikilink resolves. The target is matched exactly and case-sensitively
   against a page's filename with `.md` removed, from any depth.
4. `index.md` links every page except these three.
5. `log.md` is append-only, and each operation adds an entry beginning
   `## [YYYY-MM-DD] <op> | <subject>`. Nothing above it is ever reworded, reordered,
   deduplicated or tidied.
6. This file is never edited by the maintainer. It is the user's half of the
   arrangement, and an agent that may rewrite its own instructions has none.

## Conventions — replace these with your own

Everything from here down is a starting point, not a rule tapedeck enforces. Rewrite
it to suit what this library is actually for.

- A source page opens with the title, the channel and the date, then says what the
  video is *for* in a sentence, then walks its argument with a timestamped link per
  claim worth returning to. Quote what was said before explaining it.
- A note earns its own page when a second video touches the same thing. Until then
  the thought lives on the source page where it came up.
- Name note pages after the idea in lower-case-with-hyphens, not after the video.
- Link generously and in both directions: a source page names the ideas it raised, a
  note names the videos it came from.
- Prefer adding a paragraph to an existing note over starting a near-duplicate one.
- Say what is uncertain, and say who claimed it. The library is a record of what
  people said, not of what is true.
"""
