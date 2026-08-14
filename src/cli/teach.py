"""`help` — teaching in tiers (SPEC-cli-005).

`-h/--help` stays the terse argparse usage it has always been. `help` is the
other thing: no argument gives a one-screen tour of what tapedeck is and the
handful of verbs a person uses daily; `help <verb>` gives that verb's usage and a
worked example, because usage alone has never taught anybody a command line; and
`help manual` gives MANUAL.md, which is the manual's single source of truth and
which the installed wheel carries so the tool teaches the same thing wherever it
was installed.

The TTY discipline is the whole of the output contract here: piped, the manual is
byte-identical to the file and no pager is ever invoked, so `tapedeck help manual
| grep` works and so does redirecting it to disk. At a terminal it is paged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import Failure, Usage
from .home import DEFAULT_HOME

MANUAL_NAME = "MANUAL.md"
MANUAL = "manual"
FALLBACK_PAGER = "less -R"

EXAMPLES = {
    "add": 'tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"\n'
    'tapedeck add "https://www.youtube.com/@channel/videos"   # sweep the channel\n'
    "tapedeck add dQw4w9WgXcQ --force                        # fetch it again",
    "search": 'tapedeck search "long-running agents" -k 5\n'
    'tapedeck search sourdough --json | jq -r ".[].url"',
    "ask": 'tapedeck ask "where do these two disagree?"\n'
    'tapedeck ask "what is the 1% rule?" --fast -k 10\n'
    'tapedeck ask "what is claimed here?" --video dQw4w9WgXcQ',
    "list": "tapedeck list\ntapedeck list --json | jq length",
    "show": "tapedeck show dQw4w9WgXcQ",
    "reindex": "tapedeck reindex        # rebuilds tapedeck.db from archive/ alone",
    "rm": "tapedeck rm dQw4w9WgXcQ\ntapedeck rm dQw4w9WgXcQ --media-only    # keep the knowledge",
    "retranscribe": "tapedeck retranscribe --dry-run    # what a new model would redo\n"
    "tapedeck retranscribe",
    "adapt-parakeet": "parakeet-mlx --output-format json video.mp4 && \\\n"
    "  tapedeck adapt-parakeet < video.json > transcript.json\n"
    "# you will normally only meet this inside [transcribe] transcriber_command",
    "doctor": "tapedeck doctor\ntapedeck doctor --json",
    "setup": "tapedeck setup          # what is missing, and the command that installs it\n"
    "tapedeck setup --yes    # run exactly those commands, then check again",
    "help": "tapedeck help\ntapedeck help add\ntapedeck help manual",
}


def tour() -> str:
    return f"""\
tapedeck — a local video brain, on this machine.

Give it a YouTube URL and the video is downloaded, transcribed here, archived
as readable markdown, and indexed. Then you can find the moment something was
said, and ask questions that cite it.

    video  ->  transcript  ->  archive page  ->  search index

The video is the only source of truth; every later stage is derived from the
one before it and can be rebuilt. It all lives in $TAPEDECK_HOME (default
{DEFAULT_HOME}), a plain folder you can open.

The everyday verbs:

  add           download, transcribe, archive and index — one video, or a
                whole playlist or channel
                  tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  search        ranked timestamped excerpts, each a deep link into the video
                  tapedeck search "long-running agents" -k 5
  ask           a prose answer whose every claim cites a moment
                  tapedeck ask "what did they say about ambition?"
  list          one line per video you have
                  tapedeck list
  show          metadata and the archive page for one video
                  tapedeck show dQw4w9WgXcQ
  retranscribe  redo every transcript a better model has superseded
                  tapedeck retranscribe --dry-run

Also here: reindex, rm, doctor, setup.

  tapedeck setup          on a new machine: what is missing and what installs it
  tapedeck help <verb>    that verb's usage and a worked example
  tapedeck help manual    the whole manual
  tapedeck --version      what is installed
"""


def manual_text() -> str:
    """MANUAL.md, from the wheel that carries it or from the repo it lives in."""
    for candidate in (Path(__file__).with_name(MANUAL_NAME), _repo_manual()):
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    raise Failure(
        f"this build carries no {MANUAL_NAME} — `tapedeck help` still works, but "
        "the manual it should have shipped with is missing"
    )


def _repo_manual() -> Path:
    return Path(__file__).resolve().parents[2] / MANUAL_NAME


def emit(text: str) -> int:
    """Long output, paged only when a person is watching. Piped output is the
    bytes and nothing else — no pager, no escape sequences."""
    if sys.stdout.isatty():
        for command in (os.environ.get("PAGER"), FALLBACK_PAGER):
            if command and _page(command, text):
                return 0
    sys.stdout.write(text)
    return 0


def _page(command: str, text: str) -> bool:
    try:
        return subprocess.run(command, shell=True, input=text, text=True).returncode == 0
    except OSError:
        return False


def teach(topic: str | None, verbs: dict) -> int:
    if topic is None:
        sys.stdout.write(tour())
        return 0
    if topic == MANUAL:
        return emit(manual_text())
    parser = verbs.get(topic)
    if parser is None:
        known = ", ".join([*sorted(verbs), MANUAL])
        raise Usage(f"no help topic {topic!r} — try one of: {known}")
    example = EXAMPLES.get(topic)
    sys.stdout.write(parser.format_help())
    if example:
        sys.stdout.write(f"\nFor example:\n\n{_indent(example)}\n")
    return 0


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())
