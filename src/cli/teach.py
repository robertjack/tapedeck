"""`help`: a one-screen tour, per-verb usage plus an example, or the full
manual (SPEC-cli-005). `-h/--help` stays argparse's own terse usage.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MANUAL_NAME = "MANUAL.md"

EXAMPLES = {
    "add": 'tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"',
    "search": 'tapedeck search "agents" -k 5',
    "ask": 'tapedeck ask "what does this library say about ambition?"',
    "list": "tapedeck list",
    "show": "tapedeck show dQw4w9WgXcQ",
    "reindex": "tapedeck reindex",
    "rm": "tapedeck rm dQw4w9WgXcQ",
    "retranscribe": "tapedeck retranscribe --dry-run",
    "wiki": "tapedeck wiki file dQw4w9WgXcQ",
    "adapt-parakeet": "parakeet-mlx ... | tapedeck adapt-parakeet",
    "doctor": "tapedeck doctor",
    "setup": "tapedeck setup --yes",
    "help": "tapedeck help add",
}

TOUR = """\
tapedeck: a local video brain — download, transcribe, archive, ask.

Every video goes through the same chain: ingest -> transcribe -> archive -> index.

Everyday verbs:
  tapedeck add <url>                add a video, playlist, or channel
  tapedeck search "topic"           ranked, timestamped excerpts
  tapedeck ask "a question"         an answer from your library, cited
  tapedeck list                     every video you have added
  tapedeck show <id>                one video's metadata
  tapedeck retranscribe --dry-run   see what a model upgrade would redo

The library lives at $TAPEDECK_HOME (default ~/Tapedeck).
`tapedeck help <verb>` shows one verb's usage and an example.
`tapedeck help manual` shows the whole manual.
"""


def _manual_path() -> Path:
    packaged = Path(__file__).resolve().parent / MANUAL_NAME
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / MANUAL_NAME


def tour() -> int:
    sys.stdout.write(TOUR)
    return 0


def manual() -> int:
    try:
        text = _manual_path().read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: could not read the manual — {exc}", file=sys.stderr)
        return 1
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        pager = os.environ.get("PAGER") or "less -R"
        try:
            if subprocess.run(pager, shell=True, input=text, text=True).returncode == 0:
                return 0
        except OSError:
            pass
    sys.stdout.write(text)
    return 0


def verb(choices: dict, name: str) -> int:
    topics = sorted({*choices.keys(), "manual"})
    if name not in topics:
        print(
            f"error: unknown help topic {name!r} — known topics: {', '.join(topics)}",
            file=sys.stderr,
        )
        return 2
    if name == "manual":
        return manual()
    if name == "wiki":
        text = subprocess.run(
            [sys.executable, "-m", "wiki", "--help"], capture_output=True, text=True
        ).stdout
    else:
        text = choices[name].format_help()
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    print()
    print(EXAMPLES.get(name, f"tapedeck {name}"))
    return 0
