"""$TAPEDECK_HOME: where it is, and what a fresh one contains.

`config.toml` is the cli's only write authority in the layout contract, and it is
written exactly once — on first run — then belongs to the user. What goes into it
is every seam of SPEC-core-004 with its shipped default live and commented, so the
tools tapedeck runs are visible and editable instead of buried in code.

Not one of those defaults is written here. The fetcher's 403-proof format
selection is ingest's to publish (LESSON-0001), the whisper flags and the model
label are transcribe's (LESSON-0002), the librarian's invocation is ask's; the cli
imports each from its owner. A copy in this file would be a second source of truth
that goes quietly stale the day one of them is fixed (LESSON-0003).

`CLAUDE.md` beside it is the librarian's standing brief, which ask requires and
SPEC-ask-002 puts here rather than in an assembled prompt: it is the agent's file,
in the agent's working directory, for the user to edit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ask.seams import (
    BRIEF_NAME,
    CONFIG_NAME,
    DEFAULT_ANSWERER_COMMAND,
    DEFAULT_LIBRARIAN_COMMAND,
)
from ingest.fetch import DEFAULT_FETCHER_COMMAND, DEFAULT_LISTER_COMMAND
from transcribe.transcriber import (
    DEFAULT_MODEL,
    DEFAULT_TRANSCRIBER_COMMAND,
    PARAKEET_MODEL,
    PARAKEET_TRANSCRIBER_COMMAND,
)

DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY = "library"
ARCHIVE = "archive"


def resolve() -> Path:
    """The library home, read fresh on every run — a second library is one
    environment variable away, and neither knows about the other."""
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def prepare(home: Path) -> Path:
    """Make the home usable. Idempotent: existing files are never rewritten."""
    for directory in (home / LIBRARY, home / ARCHIVE):
        directory.mkdir(parents=True, exist_ok=True)
    _create(home / CONFIG_NAME, config_text())
    _create(home / BRIEF_NAME, BRIEF)
    return home


def _create(path: Path, text: str) -> None:
    """Write only what is not there. After first run these two files are the
    user's, and an upgrade that helpfully refreshed them would silently undo an
    edited seam — the one thing config.toml exists to hold."""
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        pass


def _toml(value: str) -> str:
    """A TOML string for a shell command. A literal string passes `"` and `$`
    through exactly as the shell must see them; a command carrying a `'` cannot be
    written that way, and falls back to a basic string, where JSON's escaping is
    TOML's."""
    return f"'{value}'" if "'" not in value else json.dumps(value)


def config_text() -> str:
    return f"""\
# tapedeck configuration — written on first run, yours from then on.
#
# Every external tool sits behind a command template (SPEC-core-004): edit the
# line and tapedeck uses the new tool, with no change to any code. Each command
# runs through your shell with its inputs in environment variables.

[ingest]
# Downloads one video. $TAPEDECK_VIDEO_ID, $TAPEDECK_VIDEO_URL, and
# $TAPEDECK_DEST — an existing directory to leave video.<ext> and its info json
# in. h264 at <=1080p by preference: YouTube serves 403s for AV1 here.
fetcher_command = {_toml(DEFAULT_FETCHER_COMMAND)}
# Expands a playlist or channel into one video id per line, in order.
# $TAPEDECK_COLLECTION_URL.
lister_command = {_toml(DEFAULT_LISTER_COMMAND)}

[transcribe]
# Audio to timestamped segments. $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID, and
# $TAPEDECK_OUT — write whisper-shaped JSON there. Turbo with conditioning off:
# large-v3 falls into repetition loops on long videos.
transcriber_command = {_toml(DEFAULT_TRANSCRIBER_COMMAND)}
# Stamped on every transcript this command makes. `tapedeck retranscribe`
# re-derives whatever disagrees with it, so a new model deserves a new label.
model = {_toml(DEFAULT_MODEL)}
#
# The published alternative — parakeet-mlx, via tapedeck's own adapter. Swap both
# lines above for these two and the next transcript comes from it:
# transcriber_command = {_toml(PARAKEET_TRANSCRIBER_COMMAND)}
# model = {_toml(PARAKEET_MODEL)}

[ask]
# The librarian (default mode): an agent turned loose in this directory with the
# brief in CLAUDE.md. The question arrives on stdin, the cited answer on stdout.
librarian_command = {_toml(DEFAULT_LIBRARIAN_COMMAND)}
# The --fast answerer: numbered source excerpts on stdin, prose back on stdout.
answerer_command = {_toml(DEFAULT_ANSWERER_COMMAND)}
"""


BRIEF = """\
# The tapedeck librarian

You are answering questions about a personal video library, from inside it. This
directory is the library, and everything you may use is in it.

## What is here

    archive/<id>.md               the readable page for one video: frontmatter,
                                  then a section per chapter, each headed by a
                                  timestamped deep link
    library/<id>/meta.json        title, channel, upload date, duration
    library/<id>/transcript.json  the timestamped segments the page was made from
    tapedeck.db                   the search index

Start with `tapedeck search "<words>"`, or grep across `archive/`, then read the
pages that look promising. Read as much as you need — there is no budget on
sources here, only on truth.

## How to answer

- Use only what these files say: no outside knowledge, no inference past them.
- Cite as you go, inline, as a markdown link to the exact moment:
  [what was said](https://www.youtube.com/watch?v=<id>&t=<seconds>s)
  The id must be a video in this library, and the offset inside its real
  duration. Every citation is checked mechanically after you answer, and one
  that does not check out fails the whole command — so cite what you read, at
  the second you read it, and never reconstruct a link from memory.
- Every answer carries at least one citation.
- If these files do not answer the question, say exactly: not in the library.
  Then, if you can, name what is here that comes nearest.
- Answer in prose: the question first, the detail after. Quote when the wording
  matters.

This file is yours to edit — house style, preferred length, what this library is
for. The librarian reads it on every question.
"""
