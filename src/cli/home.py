"""The library home: where it is, what shape it has, and its first-run scaffold.

`$TAPEDECK_HOME` is resolved on every run (SPEC-cli-001) and the home is made
whole before any verb executes, so nothing downstream wonders whether the
directories exist. The cli owns `config.toml` and writes it exactly once, with
every seam of SPEC-core-004 filled in from the default each component publishes
for itself — a fresh tapedeck works out of the box, and every external tool it
reaches for is one editable line. The librarian brief (`CLAUDE.md`) is scaffolded
the same way, because ask refuses to turn an agent loose in the library without
the grounding rules (SPEC-ask-001).

Both files are the user's from the moment they exist: scaffolding never
overwrites, so an edited config survives every later run.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from ask.seams import DEFAULT_ANSWERER_COMMAND, DEFAULT_LIBRARIAN_COMMAND
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
DIRECTORIES = (LIBRARY, ARCHIVE)
CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"
META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.json"
MEDIA_STEM = "video"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")

CONFIG_TEMPLATE = """\
# tapedeck configuration — written on first run, yours from here on.
#
# Every external tool sits behind a command template (SPEC-core-004): to change
# how tapedeck fetches, transcribes or answers, change the command, not the code.
# Each runs as a shell command with the environment noted above it; the values
# below are the defaults tapedeck ships with — edit them freely.

[ingest]
# in:  $TAPEDECK_VIDEO_URL, $TAPEDECK_VIDEO_ID, $TAPEDECK_DEST
# out: $TAPEDECK_DEST/video.<ext> and a yt-dlp-shaped info.json beside it
fetcher_command = {fetcher}
# how `tapedeck add <playlist-or-channel-url>` learns what a collection contains
# in:  $TAPEDECK_COLLECTION_URL
# out: one video id per line on stdout, in collection order
lister_command = {lister}

[transcribe]
# in:  $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID, $TAPEDECK_OUT
# out: whisper-shaped JSON ({{"segments": [{{start, end, text}}, ...]}}) at $TAPEDECK_OUT
transcriber_command = {transcriber}
# recorded in every transcript, so a better model can supersede this one later —
# change both lines together, then `tapedeck retranscribe` redoes the library
model = {model}
#
# The published alternative: parakeet-mlx, via the `tapedeck adapt-parakeet`
# filter. Swapping transcribers is these two lines and nothing else.
# transcriber_command = {parakeet_command}
# model = {parakeet_model}

[ask]
# librarian mode (the default): runs with cwd set to this directory, the question
# on stdin, and the CLAUDE.md brief beside this file as its standing instructions
librarian_command = {librarian}
# --fast mode: numbered source excerpts on stdin, prose with [n] markers on stdout
answerer_command = {answerer}
"""

BRIEF = """\
# tapedeck librarian brief

You are the librarian of this video library. Someone has asked you the question
on stdin, and your answer is going straight to them.

## What is here

- `archive/<video-id>.md` — one page per video: frontmatter (title, channel,
  upload date, duration, url), then sections headed
  `## [h:mm:ss](https://www.youtube.com/watch?v=<video-id>&t=<seconds>s) Title`.
  These pages are the readable library — start here, and grep across them.
- `library/<video-id>/meta.json` — the same metadata, structurally.
- `library/<video-id>/transcript.json` — timestamped segments, when you need the
  exact wording or a timestamp finer than a section heading.

## How to answer

1. **Only from the library.** Everything you assert must come from a file in
   this directory. If what is here does not cover the question, say so plainly —
   "that is not in the library" — and stop. Never fill the gap from your own
   knowledge, and never tell the user what they probably wanted to hear.
2. **Cite as you go.** Every claim carries an inline markdown deep link to the
   moment that supports it:
   `[what was said](https://www.youtube.com/watch?v=<video-id>&t=<seconds>s)`.
   Write them into the prose, not into a list at the end.
3. **Timestamps must be real.** Take `<seconds>` from a section heading or a
   transcript segment's `start`. Never round to something tidy, never estimate,
   never rebuild a link from memory.
4. **At least one citation.** An answer with no deep link is not an answer.
5. **A scoped question is a fence.** Asked about one video, cite only that one.

tapedeck checks every link you write after you finish: each must name a video
that is really here, at a timestamp inside its real duration. A fabricated
citation fails the whole command, so the user never sees it. Read anything here
to find the answer — but never invent where it came from.

## Style

Answer the question first, in prose. Be concrete about who said what and when.
Where the library disagrees with itself, say so and cite both sides.
"""


def toml_value(text: str) -> str:
    """TOML for a command line: a literal string keeps shell quoting readable, and
    anything with a quote of its own falls back to an escaped basic string."""
    if "'" not in text and "\n" not in text:
        return f"'{text}'"
    return json.dumps(text)  # a TOML basic string is a JSON string


def config_text() -> str:
    """The seams as each component documents them — the cli invents no defaults."""
    return CONFIG_TEMPLATE.format(
        fetcher=toml_value(DEFAULT_FETCHER_COMMAND),
        lister=toml_value(DEFAULT_LISTER_COMMAND),
        transcriber=toml_value(DEFAULT_TRANSCRIBER_COMMAND),
        model=toml_value(DEFAULT_MODEL),
        parakeet_command=toml_value(PARAKEET_TRANSCRIBER_COMMAND),
        parakeet_model=toml_value(PARAKEET_MODEL),
        librarian=toml_value(DEFAULT_LIBRARIAN_COMMAND),
        answerer=toml_value(DEFAULT_ANSWERER_COMMAND),
    )


def write_once(path: Path, text: str) -> bool:
    """Create `path` if it is not there. True when we wrote it; an existing file is
    never reopened — after the first run these are the user's files, not ours."""
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except FileExistsError:
        return False
    return True


def resolve() -> Path:
    """The library home, scaffolded if this is its first use."""
    home = Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()
    fresh = not home.exists()
    for name in DIRECTORIES:
        (home / name).mkdir(parents=True, exist_ok=True)
    write_once(home / CONFIG_NAME, config_text())
    write_once(home / BRIEF_NAME, BRIEF)
    if fresh:
        print(f"created a new tapedeck home at {home}", file=sys.stderr)
    return home


def entry(home: Path, video_id: str) -> Path:
    """`library/<id>/` — the video and everything derived from it."""
    return home / LIBRARY / video_id


def page(home: Path, video_id: str) -> Path:
    """`archive/<id>.md` — the readable render, and the index's only source."""
    return home / ARCHIVE / f"{video_id}.md"


def entries(home: Path) -> list[str]:
    """Every video the library holds, in id order. A dotted directory is a fetch
    in flight or a crashed one, not a video."""
    library = home / LIBRARY
    found = sorted(library.iterdir()) if library.is_dir() else []
    return [path.name for path in found if path.is_dir() and not path.name.startswith(".")]


def media(entry_dir: Path) -> list[Path]:
    """`library/<id>/video.<ext>` — the download itself, never a sidecar. The
    layout contract names the file without fixing the container."""
    contents = entry_dir.iterdir() if entry_dir.is_dir() else []
    return sorted(
        path
        for path in contents
        if path.is_file() and path.stem == MEDIA_STEM and path.suffix.lower() != ".json"
    )


def ingested(home: Path, video_id: str) -> bool:
    """Whether this video is already downloaded — the question ingest asks before
    skipping a fetch (SPEC-core-003), asked a moment earlier so a sweep can say
    which of its videos it actually added."""
    where = entry(home, video_id)
    return bool(media(where)) and (where / META_NAME).is_file()
