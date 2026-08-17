"""`help` (SPEC-cli-005): a one-screen tour, per-verb usage plus a worked
example, and the manual — byte-identical to MANUAL.md when stdout is piped.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .home import DISPLAY_DEFAULT_HOME

TOPICS = (
    "add", "search", "ask", "list", "show", "reindex", "rm", "retranscribe",
    "wiki", "adapt-parakeet", "doctor", "setup", "manual",
)

EXAMPLES = {
    "add": "tapedeck add https://youtu.be/dQw4w9WgXcQ",
    "search": 'tapedeck search "agents" -k 5',
    "ask": 'tapedeck ask "what is the core idea?"',
    "list": "tapedeck list --json",
    "show": "tapedeck show dQw4w9WgXcQ",
    "reindex": "tapedeck reindex",
    "rm": "tapedeck rm dQw4w9WgXcQ --media-only",
    "retranscribe": "tapedeck retranscribe --dry-run",
    "adapt-parakeet": "tapedeck adapt-parakeet < parakeet.json > whisper.json",
    "doctor": "tapedeck doctor --json",
    "setup": "tapedeck setup --yes",
}


def manual_path() -> Path:
    """The installed copy sits beside this module (pyproject's force-include,
    SPEC-cli-005); a repo checkout falls back to the root the package is
    generated under."""
    here = Path(__file__).resolve().parent
    local = here / "MANUAL.md"
    if local.is_file():
        return local
    return here.parents[1] / "MANUAL.md"


def _tour() -> str:
    return f"""tapedeck — a local video brain: download, transcribe, archive, ask.

Everything lives in the library home (default {DISPLAY_DEFAULT_HOME}; override
with $TAPEDECK_HOME). Every video moves through one chain:

    video -> transcript -> archive page -> search index

Start here:
  tapedeck add <url>              {EXAMPLES['add']}
  tapedeck search <query>         {EXAMPLES['search']}
  tapedeck ask <question>         {EXAMPLES['ask']}
  tapedeck list                   {EXAMPLES['list']}
  tapedeck show <id>              {EXAMPLES['show']}
  tapedeck retranscribe           {EXAMPLES['retranscribe']}

More: tapedeck help <verb> | tapedeck help manual | tapedeck doctor
"""


def cmd_help(args, home, subparsers: dict) -> int:
    topic = args.topic
    if topic is None:
        print(_tour())
        return 0
    if topic == "manual":
        return _show_manual()
    if topic == "wiki":
        return _wiki_help()
    if topic in subparsers:
        print(subparsers[topic].format_help())
        example = EXAMPLES.get(topic)
        if example:
            print(f"Example:\n  {example}")
        return 0
    print(
        f"error: unknown help topic {topic!r} — try: {', '.join(TOPICS)}",
        file=sys.stderr,
    )
    return 2


def _wiki_help() -> int:
    result = subprocess.run([sys.executable, "-m", "wiki", "--help"], capture_output=True, text=True)
    print(result.stdout, end="")
    print("Example:\n  tapedeck wiki file dQw4w9WgXcQ")
    return 0


def _show_manual() -> int:
    text = manual_path().read_text(encoding="utf-8")
    stream = sys.stdout
    if stream.isatty() and not os.environ.get("NO_COLOR"):
        _page(text)
    else:
        stream.write(text)
    return 0


def _page(text: str) -> None:
    for pager in filter(None, (os.environ.get("PAGER"), "less -R")):
        try:
            result = subprocess.run(pager, shell=True, input=text, text=True)
        except OSError:
            continue
        if result.returncode == 0:
            return
    sys.stdout.write(text)
