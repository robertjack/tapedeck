"""`help`, in tiers: a tour, a verb, or the whole manual (SPEC-cli-005).

`-h/--help` stays what argparse makes it — terse, complete, for someone who
already knows the shape of the tool. This is the other audience: `help` alone is
one screen that assumes nothing, `help <verb>` is that verb's usage with a worked
example under it, and `help manual` is MANUAL.md itself.

MANUAL.md at the repo root is the manual's single source of truth and the wheel
carries a copy beside this module, so the installed tool teaches the same thing
the repository does. Piped, `help manual` is that file byte for byte: no header,
no pager, no colour — it is a file you can diff, redirect, or feed to something
else. The niceties are for a terminal only, and `NO_COLOR` turns them off there.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import USAGE, Failure

MANUAL_NAME = "MANUAL.md"
MANUAL_TOPIC = "manual"
DEFAULT_PAGER = "less -R"
BOLD, RESET = "\x1b[1m", "\x1b[0m"

TOUR = """\
tapedeck — a local video brain.

  Give it a YouTube URL: the video is downloaded, transcribed on this machine,
  archived as readable markdown, and indexed. From then on you can search the
  exact moment something was said, and ask questions that come back cited with
  timestamped links into the videos.

  It all lives in ~/Tapedeck — plain files you can open. $TAPEDECK_HOME moves it.

The chain. Every stage is a file, and every arrow can be run again:

  video  ->  transcript  ->  archive page  ->  search index

The everyday verbs:

  add           fetch, transcribe, archive, index — one video, or a whole channel
                  tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  search        ranked, timestamped excerpts, each a deep link
                  tapedeck search "long-running agents" -k 5
  ask           an answer from your library, with its citations checked
                  tapedeck ask "what did she say about ambition?"
  list          one line per video: id, date, channel, title
                  tapedeck list
  show          metadata and the archive page for one video
                  tapedeck show dQw4w9WgXcQ
  retranscribe  re-derive every transcript a better model has superseded
                  tapedeck retranscribe --dry-run

Also here: reindex (rebuild the search index), rm (remove a video, or just its
media), adapt-parakeet (the filter behind an alternative transcriber).

Going further:

  tapedeck help <verb>     that verb's usage, and an example
  tapedeck help manual     the full manual
  tapedeck --version       the installed version
"""

# One worked example per verb — the line someone can paste, not a paraphrase of
# the usage above it.
EXAMPLES = {
    "add": (
        'tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"\n'
        'tapedeck add "https://www.youtube.com/@channel/videos"   # the whole channel\n'
        "tapedeck add dQw4w9WgXcQ --force                        # re-fetch just this one"
    ),
    "search": (
        'tapedeck search "sourdough starter" -k 3\n'
        'tapedeck search "agents" --json | jq -r ".[].url"'
    ),
    "ask": (
        'tapedeck ask "how do long-running agents fail?"\n'
        'tapedeck ask "what is the 1% rule?" --video dQw4w9WgXcQ\n'
        'tapedeck ask "what is chunking for?" --fast -k 10'
    ),
    "list": "tapedeck list\ntapedeck list --json | jq length",
    "show": "tapedeck show dQw4w9WgXcQ\ntapedeck show dQw4w9WgXcQ --json",
    "reindex": "tapedeck reindex        # after a lost or stale tapedeck.db",
    "rm": (
        "tapedeck rm dQw4w9WgXcQ                # forget it everywhere\n"
        "tapedeck rm dQw4w9WgXcQ --media-only   # keep the knowledge, free the disk"
    ),
    "retranscribe": (
        "tapedeck retranscribe --dry-run   # what a new [transcribe].model would redo\n"
        "tapedeck retranscribe             # redo it"
    ),
    "adapt-parakeet": (
        "# inside [transcribe].transcriber_command, never by hand:\n"
        'parakeet-mlx --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" '
        '"$TAPEDECK_MEDIA" && tapedeck adapt-parakeet < ... > "$TAPEDECK_OUT"'
    ),
    "help": "tapedeck help\ntapedeck help add\ntapedeck help manual",
}


def decorated(stream=None) -> bool:
    """Whether this run may dress its output up at all — ANSI or a pager.

    Both answer to the same question, because both mean the same thing: is there
    a person at the other end of this? Piped output and `NO_COLOR` say no.
    """
    stream = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def teach(verbs: dict, topic: str | None, stream=None) -> int:
    """`help`, `help <verb>`, `help manual` — the three tiers.

    `verbs` maps each verb to its argparse subparser, so a verb's tier is the
    same usage `-h` prints and cannot drift from the surface it documents.
    """
    stream = sys.stdout if stream is None else stream
    if topic is None:
        return tour(stream)
    if topic == MANUAL_TOPIC:
        return manual(stream)
    if topic in verbs:
        return _verb(verbs[topic], topic, stream)
    known = ", ".join([*verbs, MANUAL_TOPIC])
    raise Failure(f"no help for {topic!r} — topics are: {known}", code=USAGE)


def tour(stream=None) -> int:
    stream = sys.stdout if stream is None else stream
    stream.write(_headings(TOUR, decorated(stream)))
    return 0


def _headings(text: str, on: bool) -> str:
    """Bold the lines that carry the structure, and only in a terminal."""
    if not on:
        return text
    lines = [
        f"{BOLD}{line}{RESET}" if line and not line.startswith(" ") else line
        for line in text.split("\n")
    ]
    return "\n".join(lines)


def _verb(subparser, topic: str, stream) -> int:
    stream.write(subparser.format_help().rstrip("\n") + "\n")
    example = EXAMPLES.get(topic)
    if example:
        stream.write("\nExample:\n\n")
        stream.write("\n".join(f"    {line}" for line in example.split("\n")) + "\n")
    return 0


def manual_path() -> Path | None:
    """The manual this build carries: beside the module when installed from the
    wheel, at the repo root when running from a checkout."""
    here = Path(__file__).resolve().parent
    for directory in (here, *here.parents[:2]):
        candidate = directory / MANUAL_NAME
        if candidate.is_file():
            return candidate
    return None


def manual(stream=None) -> int:
    stream = sys.stdout if stream is None else stream
    path = manual_path()
    if path is None:
        raise Failure(
            f"this build carries no {MANUAL_NAME} — the manual ships with the "
            "package, so a build without one is incomplete"
        )
    text = path.read_text(encoding="utf-8")
    if decorated(stream) and _page(text):
        return 0
    stream.write(text)  # byte for byte, exactly the file
    return 0


def _page(text: str) -> bool:
    """Show the manual through a pager, or say it could not be done.

    $PAGER first, `less -R` after it, and if neither is here the caller prints
    the text plainly — a missing pager is not a reason to withhold the manual.
    """
    chosen = (os.environ.get("PAGER") or "").strip()
    tried = [command for command in (chosen, DEFAULT_PAGER) if command]
    for command in dict.fromkeys(tried):
        try:
            result = subprocess.run(command, shell=True, input=text, text=True)
        except OSError:
            continue
        if result.returncode == 0:
            return True
    return False
