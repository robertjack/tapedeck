"""`help` teaches in tiers (SPEC-cli-005): a tour, a verb, or the whole manual.

`-h/--help` stays what argparse makes of it — terse, complete, and no use at all
to someone who has just installed this. These are the other thing: one screen for
a newcomer, usage plus a worked example for someone who knows a verb's name, and
MANUAL.md for someone who wants all of it.

MANUAL.md at the repo root is the manual's single source of truth, so this module
locates that file and never restates a line of it. Piped, it comes out verbatim —
a manual a redirect reshapes is a different document, and `tapedeck help manual >
manual.md` should give back the file. The niceties are strictly for people at a
terminal: highlighting when there is one and `$NO_COLOR` is unset, `$PAGER` when
there is something to page into.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import Failure

MANUAL = "manual"
MANUAL_NAME = "MANUAL.md"
# Beside the package first — an installed tapedeck carries its manual — then the
# repo root, which is where it lives when tapedeck is run from a checkout.
MANUAL_CANDIDATES = (
    Path(__file__).resolve().parent / MANUAL_NAME,
    Path(__file__).resolve().parents[2] / MANUAL_NAME,
)
FALLBACK_PAGER = "less -R"
BOLD, RESET = "\x1b[1m", "\x1b[0m"

TOUR = """\
tapedeck — a local video brain.

  Add a YouTube URL and the video is downloaded, transcribed on this machine,
  archived as readable markdown, and indexed. Nothing leaves the machine but the
  download itself; everything lives in $TAPEDECK_HOME (~/dev/storage/tapedeck).

The derivation chain, every arrow re-runnable:

  video  ->  transcript  ->  archive page  ->  search index

The video is the only source of truth. Delete anything downstream of it and one
verb builds it back.

The everyday verbs:

  tapedeck add "https://youtu.be/dQw4w9WgXcQ"     fetch, transcribe, archive, index
  tapedeck search "long-running agents" -k 5      timestamped excerpts, deep links
  tapedeck ask "what did they say about X?"       a cited answer from the library
  tapedeck list                                   one line per video
  tapedeck show dQw4w9WgXcQ                       metadata and the archive path
  tapedeck retranscribe --dry-run                 what a better model would redo

A playlist or channel URL adds every video it names and skips what is already
here, so re-running that URL is how you pick up new uploads.

Also here: reindex, rm, adapt-parakeet.

Read on:

  tapedeck help <verb>     that verb's usage, with a worked example
  tapedeck help manual     the whole manual
"""

EXAMPLES = {
    "add": """\
    tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    tapedeck add dQw4w9WgXcQ --force                  # re-fetch that one video
    tapedeck add "https://www.youtube.com/@channel/videos"   # every video in it\
""",
    "search": """\
    tapedeck search "long-running agents" -k 5
    tapedeck search sourdough --json | jq -r '.[].url'\
""",
    "ask": """\
    tapedeck ask "what does the library say about ambition?"
    tapedeck ask "how do agents fail?" --fast -k 10    # retrieval, no agent
    tapedeck ask "what's the 1% rule?" --video dQw4w9WgXcQ\
""",
    "list": """\
    tapedeck list
    tapedeck list --json | jq -r '.[] | .id + "  " + .title'\
""",
    "show": """\
    tapedeck show dQw4w9WgXcQ
    tapedeck show dQw4w9WgXcQ --json | jq -r .archive\
""",
    "reindex": """\
    tapedeck reindex        # rebuilds tapedeck.db from archive/ alone\
""",
    "rm": """\
    tapedeck rm dQw4w9WgXcQ                # forget it everywhere
    tapedeck rm dQw4w9WgXcQ --media-only   # keep the knowledge, free the disk\
""",
    "retranscribe": """\
    tapedeck retranscribe --dry-run   # what a new [transcribe] model would redo
    tapedeck retranscribe             # re-transcribe, re-render, re-index\
""",
    "adapt-parakeet": """\
    parakeet-mlx --output-format json video.mp4 && \\
      tapedeck adapt-parakeet < video.json > "$TAPEDECK_OUT"\
""",
    "help": """\
    tapedeck help add
    tapedeck help manual | less\
""",
}


def topics(choices) -> list[str]:
    return [*choices, MANUAL]


def teach(choices, topic: str | None, out=None) -> int:
    """One of the three tiers, or a usage error naming what it knows."""
    out = out or sys.stdout
    if topic is None:
        out.write(paint(TOUR, out))
        return 0
    if topic == MANUAL:
        return manual(out)
    if topic in choices:
        out.write(verb(choices, topic))
        return 0
    raise Failure(
        f"no help topic {topic!r} — known topics: {', '.join(topics(choices))}",
        code=2,
    )


def verb(choices, name: str) -> str:
    """A verb's own usage, then what using it actually looks like. The usage half
    is argparse's, taken from the parser the cli really runs, so it cannot come to
    describe flags this build does not have."""
    example = EXAMPLES.get(name, f"    tapedeck {name}")
    return f"{choices[name].format_help().rstrip()}\n\nExample:\n\n{example}\n"


def manual_path() -> Path:
    for candidate in MANUAL_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise Failure(
        f"{MANUAL_NAME} is not installed beside tapedeck — `tapedeck help` still "
        "gives the tour, and the manual lives at the repo root"
    )


def manual(out) -> int:
    try:
        text = manual_path().read_text(encoding="utf-8")
    except OSError as exc:
        raise Failure(f"could not read {MANUAL_NAME} — {exc}") from exc
    if out.isatty():
        for pager in (os.environ.get("PAGER"), FALLBACK_PAGER):
            if pager and pager.strip() and _page(pager, text):
                return 0
    # Not a terminal, or no pager that would take it: the file, byte for byte.
    out.write(text)
    return 0


def _page(pager: str, text: str) -> bool:
    """True when the pager took the manual. A pager that is not installed, or
    that fails, is not an error — it just means printing it plainly."""
    try:
        return subprocess.run(pager, shell=True, input=text, text=True).returncode == 0
    except OSError:
        return False


def paint(text: str, out) -> str:
    """The tour, highlighted only when someone is looking at it. Redirected, or
    with $NO_COLOR set, the same bytes come out plain — a tour saved to a file
    full of escape sequences is a worse tour."""
    if not out.isatty() or os.environ.get("NO_COLOR"):
        return text
    lines = [
        f"{BOLD}{line}{RESET}" if line[:1].isalpha() and line.endswith(":") else line
        for line in text.splitlines()
    ]
    return "\n".join(lines) + "\n"
