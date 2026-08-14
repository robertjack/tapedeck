"""`$TAPEDECK_HOME`: where the library is, and what a fresh one starts with.

Resolved on every run and created on first use (SPEC-cli-001). Two files are the
cli's to write, both exactly once: `config.toml`, because a seam nobody can see
is a seam nobody can change (SPEC-core-004), and `CLAUDE.md`, the standing brief
the librarian reads in the directory it works in. Neither is ever rewritten —
after the first run they are the user's, and a tapedeck that silently restored
its own defaults over an edit would make the config a suggestion.

The defaults themselves belong to the components that run them: ingest's fetcher
and lister, transcribe's transcriber and model label, ask's librarian and
answerer. They are imported, not retyped, so a fresh install ships whatever those
components currently know — including the incidents already paid for once
(LESSON-0001's avc1 preference, LESSON-0002's conditioning flag and label).
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

DEFAULT_HOME = "~/dev/storage/tapedeck"
CONFIG_NAME = "config.toml"
BRIEF_NAME = "CLAUDE.md"
LIBRARY = "library"
ARCHIVE = "archive"


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def toml_string(value: str) -> str:
    """A command as TOML. Literal-quoted, because a shell command is full of the
    characters a basic string would eat — `$`, `\\`, `"` — and a config the user
    edits should read exactly like the command they would type."""
    if "'" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def config_text() -> str:
    """The first-run config: the shipped defaults, spelled out, with the reason
    each is what it is — and the published alternative commented beside it."""
    return f"""\
# tapedeck configuration — written on first run and never rewritten. From here on
# it is yours: no tapedeck command edits this file.
#
# Every external tool tapedeck runs is a command template here (SPEC-core-004), so
# changing fetcher, transcriber or answerer is an edit to this file and never to
# tapedeck. Below are the shipped defaults, written out rather than implied, each
# with what running it for real has taught.

[ingest]
# Downloads one video. Env: TAPEDECK_VIDEO_ID, TAPEDECK_VIDEO_URL, TAPEDECK_DEST
# (an existing directory) — leave video.<ext> and a yt-dlp-shaped info.json in it.
# h264 at <=1080p is preferred deliberately: YouTube answers AV1 requests here
# with 403s, and a solved incident is only solved if it ships (LESSON-0001).
fetcher_command = {toml_string(DEFAULT_FETCHER_COMMAND)}

# Lists a playlist or channel: one video id per line on stdout.
# Env: TAPEDECK_COLLECTION_URL. `tapedeck add <channel-url>` sweeps what it prints,
# and re-running the same URL later picks up only what is new.
lister_command = {toml_string(DEFAULT_LISTER_COMMAND)}

[transcribe]
# Transcribes one video. Env: TAPEDECK_MEDIA, TAPEDECK_VIDEO_ID, TAPEDECK_OUT —
# write whisper-shaped JSON ({{"segments": [{{"start", "end", "text"}}]}}) to
# $TAPEDECK_OUT. `--condition-on-previous-text False` is not decoration: without
# it large-v3 falls into repetition loops on quiet passages (LESSON-0002).
transcriber_command = {toml_string(DEFAULT_TRANSCRIBER_COMMAND)}

# Stamped on every transcript this seam produces, and the whole of how tapedeck
# knows one is out of date: `tapedeck retranscribe` re-derives every video whose
# label is not this string. Change the command, change this with it.
model = {toml_string(DEFAULT_MODEL)}

# The published alternative (SPEC-transcribe-002): parakeet-mlx, adapted to the
# whisper shape by tapedeck's own `adapt-parakeet` filter. Swapping transcriber is
# these two lines and nothing else — then `tapedeck retranscribe` to catch up.
# transcriber_command = {toml_string(PARAKEET_TRANSCRIBER_COMMAND)}
# model = {toml_string(PARAKEET_MODEL)}

[ask]
# The librarian (default mode): the question on stdin, prose with inline deep-link
# citations on stdout, run in this directory so it reads CLAUDE.md and the archive
# beside it. Every citation it writes is checked against the library afterwards.
librarian_command = {toml_string(DEFAULT_LIBRARIAN_COMMAND)}

# `ask --fast`: the retrieved passages arrive on stdin, the prose comes back on
# stdout with [n] markers. tapedeck assembles the Sources list, never this command.
answerer_command = {toml_string(DEFAULT_ANSWERER_COMMAND)}
"""


BRIEF_TEXT = """\
# The tapedeck library

You are the librarian of this directory. It holds one person's watched videos:
`archive/<video-id>.md` is a readable page per video — metadata, then timestamped
sections — `library/<video-id>/` holds the video with its `meta.json` and
`transcript.json`, and `tapedeck.db` is a full-text index over the archive pages.

Answer from what is here and nothing else. Read the archive pages: grep them,
follow the timestamps, quote what was actually said.

Cite every claim with a deep link to the moment it came from, inline in the prose:

    [what is said there](https://www.youtube.com/watch?v=<video-id>&t=<seconds>s)

Each link must name a video that is in this library and a second that really falls
inside it. tapedeck checks every citation against the library after you answer and
refuses the whole answer if one cannot be traced; an answer with no citation at
all is refused the same way. Do not guess a timestamp — read it off the page.

If these files do not answer the question, say that it is not in the library. That
is a true answer. A plausible one from what you already know about the subject is
not, and is the one failure this library cannot tolerate.
"""


def scaffold(home: Path) -> Path:
    """Make sure the home exists, with the two files the cli owns. Idempotent:
    what is already there is left exactly as it is."""
    (home / LIBRARY).mkdir(parents=True, exist_ok=True)
    (home / ARCHIVE).mkdir(parents=True, exist_ok=True)
    _write_once(home / CONFIG_NAME, config_text())
    _write_once(home / BRIEF_NAME, BRIEF_TEXT)
    return home


def _write_once(path: Path, text: str) -> None:
    """Create, or leave alone. `x` mode asks the filesystem rather than looking
    first, so two tapedecks starting at once cannot both decide it is missing."""
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError:
        pass
