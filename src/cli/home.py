"""Where the library is, and what a fresh one starts with.

The cli resolves `$TAPEDECK_HOME` on every run and is the only component allowed
to decide what it means (SPEC-cli-001) — every other component is handed the
answer in its environment, so a stale default anywhere else can never be reached.

The default is `~/Tapedeck`: a plain, visible directory in whoever's home this
is. The archive pages are the point of the tool and they are meant to be opened,
so the library does not hide in a platform-private application directory, and it
is certainly not a path off the author's disk.

First use scaffolds the home: the directories, a `config.toml` of commented
defaults, and the librarian's brief. The seam defaults are imported from the
components that own them (SPEC-core-004, LESSON-0003) — config.toml is the cli's
file to write, but the shape of a seam belongs to whoever runs it, and a copy
here would drift from the real one in silence.
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

HOME_VAR = "TAPEDECK_HOME"
DEFAULT_HOME = "~/Tapedeck"
LIBRARY = "library"
ARCHIVE = "archive"
CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"


def resolve() -> Path:
    """The library home for this run. `$TAPEDECK_HOME` is taken verbatim — the
    only liberty is `~`, which a variable set in a config file may still carry."""
    setting = (os.environ.get(HOME_VAR) or "").strip()
    return Path(setting or DEFAULT_HOME).expanduser()


def prepare() -> Path:
    """The home, ready to be used: directories present, first-run files written.

    Only ever additive. An existing `config.toml` or `CLAUDE.md` is the user's
    file from the moment it exists (library-layout.md), so a later run reads it
    and leaves it exactly as it found it.
    """
    home = resolve()
    for name in (LIBRARY, ARCHIVE):
        (home / name).mkdir(parents=True, exist_ok=True)
    _write_once(home / CONFIG_NAME, config_text())
    _write_once(home / BRIEF_NAME, BRIEF_TEXT)
    return home


def _write_once(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _toml(value: str) -> str:
    """A TOML string that reads back as exactly this command.

    The seam commands are shell lines full of double quotes and `$VARIABLES`, so
    they are written as literal strings — no escaping, and nothing in them can be
    mistaken for TOML syntax on the way back in.
    """
    if "'" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def config_text() -> str:
    """The first-run `config.toml`: every seam, its inputs, and its default.

    The defaults are the ones the components publish, which is how a fresh
    install ships with the incidents already solved — h264 rather than the AV1
    YouTube 403s on (LESSON-0001), whisper turbo with conditioning off rather
    than the large-v3 repetition loop (LESSON-0002).
    """
    return f"""\
# tapedeck configuration — written once on first run, yours from then on.
#
# Every external tool sits behind a command template (SPEC-core-004): to change
# the tool, edit the line — never tapedeck. Each command runs through a shell
# with its inputs in the environment, named in the comment above it.

[ingest]
# Downloads one video. Set: $TAPEDECK_VIDEO_ID, $TAPEDECK_VIDEO_URL, and
# $TAPEDECK_DEST (an existing directory). Leave video.<ext> and a yt-dlp-shaped
# info.json in $TAPEDECK_DEST. The format preference is deliberate: YouTube
# serves 403s for AV1 here, so h264 at <=1080p is asked for first.
fetcher_command = {_toml(DEFAULT_FETCHER_COMMAND)}
# Lists the video ids of a playlist or channel, one per line, on stdout.
# Set: $TAPEDECK_COLLECTION_URL. Used by `tapedeck add <playlist-or-channel>`.
lister_command = {_toml(DEFAULT_LISTER_COMMAND)}

[transcribe]
# Turns a video into timestamped segments. Set: $TAPEDECK_MEDIA (the video),
# $TAPEDECK_VIDEO_ID, and $TAPEDECK_OUT (where to write). Leave whisper-shaped
# JSON — {{"segments": [{{"start", "end", "text"}}, ...]}} — at $TAPEDECK_OUT.
transcriber_command = {_toml(DEFAULT_TRANSCRIBER_COMMAND)}
# Stamped on every transcript this command makes. `tapedeck retranscribe`
# re-derives every video whose label differs from this one, so a new model — or
# a changed flag — deserves a new label.
model = {_toml(DEFAULT_MODEL)}

# The published alternative: parakeet-mlx, through the adapt-parakeet filter
# that ships with tapedeck. Swapping transcriber is these two lines and nothing
# else. Uncomment them, comment the pair above, then `tapedeck retranscribe`.
# transcriber_command = {_toml(PARAKEET_TRANSCRIBER_COMMAND)}
# model = {_toml(PARAKEET_MODEL)}

[ask]
# The librarian (default mode): an agent turned loose in this directory with the
# question on stdin and CLAUDE.md as its standing brief. It answers in prose with
# inline deep links, and tapedeck checks every one of them before printing.
librarian_command = {_toml(DEFAULT_LIBRARIAN_COMMAND)}
# The --fast answerer: numbered excerpts in on stdin, prose with [n] markers out.
# It needs no tools — its sources are the retrieval tapedeck hands it.
answerer_command = {_toml(DEFAULT_ANSWERER_COMMAND)}
"""


# The librarian reads this as the CLAUDE.md of the directory it is dropped into,
# which is why the grounding rules live in a file the user can edit rather than
# in a prompt tapedeck assembles. Every rule here is also enforced mechanically
# after the answer comes back (contracts/ask-citations.md) — the brief is how the
# agent learns what it is being held to, not how it is held to it.
BRIEF_TEXT = """\
# The librarian's brief

You are answering questions about a tapedeck library: a collection of videos
that have been downloaded, transcribed, and archived on this machine.

## What is here

- `archive/<id>.md` — one readable page per video: frontmatter (title, channel,
  upload date, duration, url), then the transcript in timestamped sections.
  These pages are the fastest way to read a video, and grep is your friend.
- `library/<id>/meta.json` — the same metadata, structurally.
- `library/<id>/transcript.json` — the raw timestamped segments.
- `tapedeck.db` — a full-text index; you do not need to read it.

## How to answer

- Answer only from what the library actually says. If the library does not
  cover the question, say plainly that it is not in the library — a confident
  answer from your own knowledge is the one failure that matters here.
- Cite every claim with an inline markdown deep link to the moment it came
  from: `[what was said](https://www.youtube.com/watch?v=<id>&t=<seconds>s)`.
  The seconds come from the section timestamp nearest the words you used.
- An answer with no citation is not printed, and a citation to a video that is
  not in this library, or to a moment past the end of one, fails the command.
  Never guess an id or a timestamp: read it from the page you used.
- Quote sparingly and attribute who is speaking when the videos disagree.

This file is yours to edit: house style, preferred length, and what this
library is for all belong here.
"""
