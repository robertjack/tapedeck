"""$TAPEDECK_HOME: where the library is, and what a first run puts there.

SPEC-cli-001. The default home belongs to whoever installed the tool, not to its
author: `~/Tapedeck`, a plain visible directory in the user's own home. The
archive pages are meant to be opened, so it is never hidden and never a
platform-private application directory, and never a path particular to one
machine. `$TAPEDECK_HOME` overrides it verbatim, it is resolved on every run, and
every path the cli touches derives from what `resolve()` returns.

`config.toml` is the one file the cli owns. What goes in it is not the cli's to
invent: each seam's default is published by the component that runs it
(SPEC-core-004), so a fresh install inherits every lesson those defaults carry —
the avc1 format preference, the turbo weights with conditioning off — without
this module having to know why they are there. The parakeet alternative is
written in beside the whisper default as a comment, exactly as
SPEC-transcribe-002 publishes it: proof that changing transcriber is an edit to
this file and not to tapedeck.
"""

from __future__ import annotations

import os
from pathlib import Path

from ask.seams import DEFAULT_ANSWERER_COMMAND, DEFAULT_LIBRARIAN_COMMAND
from ingest import DEFAULT_FETCHER_COMMAND, DEFAULT_LISTER_COMMAND
from transcribe import (
    DEFAULT_MODEL,
    DEFAULT_TRANSCRIBER_COMMAND,
    PARAKEET_MODEL,
    PARAKEET_TRANSCRIBER_COMMAND,
)

DEFAULT_HOME = "~/Tapedeck"
CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"
# The directories of system/contracts/library-layout.md. Their contents belong to
# other components; the cli only guarantees they exist.
LIBRARY = "library"
ARCHIVE = "archive"


def resolve() -> Path:
    """The library home for this run — the cli is the sole authority on it."""
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def scaffold(home: Path) -> Path:
    """Make a home usable, once. Nothing already here is ever rewritten: after the
    first run config.toml and the brief are the user's files, not ours."""
    (home / LIBRARY).mkdir(parents=True, exist_ok=True)
    (home / ARCHIVE).mkdir(parents=True, exist_ok=True)
    _create(home / CONFIG_NAME, config_text())
    _create(home / BRIEF_NAME, BRIEF)
    return home


def _create(path: Path, text: str) -> None:
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        pass


def _toml(value: str) -> str:
    """A TOML string for a shell command. Command templates are thick with double
    quotes and thin on single ones, so a literal string carries them exactly as
    the owning component published them — there is no escaping to get wrong."""
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def config_text() -> str:
    """The first-run config.toml: every seam visible, commented, and editable."""
    return f"""\
# tapedeck configuration — this file is yours to edit.
#
# Every external tool sits behind a command template (SPEC-core-004): change a
# line here and tapedeck uses the new tool, with no change to tapedeck itself.
# Each template runs through a shell with its inputs in environment variables,
# named in the comment above it. `tapedeck doctor` reads this file to decide
# which tools to check for, so a swapped seam changes what it looks for too.

[ingest]
# Downloads one video. In: $TAPEDECK_VIDEO_ID, $TAPEDECK_VIDEO_URL,
# $TAPEDECK_DEST (an existing directory). Out: video.<ext> plus a
# yt-dlp-shaped info.json in $TAPEDECK_DEST.
# h264 at <=1080p is preferred on purpose: YouTube serves 403s for AV1 here.
fetcher_command = {_toml(DEFAULT_FETCHER_COMMAND)}

# Expands a playlist or channel URL into video ids, one per line.
# In: $TAPEDECK_COLLECTION_URL. Out: the ids, on stdout.
lister_command = {_toml(DEFAULT_LISTER_COMMAND)}

[transcribe]
# Audio to timestamped segments. In: $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID,
# $TAPEDECK_OUT. Out: whisper-shaped JSON written to $TAPEDECK_OUT.
# Turbo weights with conditioning off: large-v3 with conditioning left on falls
# into repetition loops on long videos.
transcriber_command = {_toml(DEFAULT_TRANSCRIBER_COMMAND)}

# The label stamped on every transcript, and what `tapedeck retranscribe`
# compares against to decide which transcripts a better model has superseded.
# A new model deserves a new label, or the old transcripts are unreachable.
model = {_toml(DEFAULT_MODEL)}

# The published alternative: parakeet-mlx, with `tapedeck adapt-parakeet`
# turning its JSON into the shape this seam reads. Swap in these two lines and
# nothing else changes.
# transcriber_command = {_toml(PARAKEET_TRANSCRIBER_COMMAND)}
# model = {_toml(PARAKEET_MODEL)}

[ask]
# The default `ask` agent. It is dropped into the library home with read-only
# tools and the standing brief in CLAUDE.md, and answers in prose with inline
# deep-link citations — which tapedeck then verifies against the library.
librarian_command = {_toml(DEFAULT_LIBRARIAN_COMMAND)}

# The `ask --fast` answerer: numbered excerpts on stdin, prose on stdout.
# tapedeck assembles the Sources section itself, never the answerer.
answerer_command = {_toml(DEFAULT_ANSWERER_COMMAND)}
"""


BRIEF = """\
# The tapedeck librarian

You are answering questions from a library of transcribed videos, and it is the
directory you are standing in. Everything you may use is here:

- `archive/<id>.md` — one readable page per video: frontmatter, then a section
  per chapter, each heading a `[h:mm:ss](deep link)` into the video itself.
- `library/<id>/meta.json` — title, channel, upload date, duration.
- `library/<id>/transcript.json` — the timestamped segments the page renders.

The rules, in order of importance:

1. Answer only from what you read here. If these videos do not cover the
   question, say plainly that it is not in the library, and stop. A confident
   answer from your own memory is the one failure that matters.
2. Cite every claim with an inline markdown deep link:
   `[what was said](https://www.youtube.com/watch?v=<id>&t=<seconds>s)`.
   An answer carrying no citation is refused before the user ever sees it.
3. A citation must point at a video in this library, at a moment inside its real
   duration. Take the id and the seconds from the page you read them on — never
   reconstruct one from memory. Citations are checked mechanically, and a
   fabricated one fails the whole command.
4. Quote what was actually said, then explain it. Read enough of a page to be
   right: grep is for finding, not for understanding.

This file is yours to edit — house style, preferred length, and what this
particular library is for all belong here.
"""
