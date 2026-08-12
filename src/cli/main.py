"""Boundary: the `tapedeck` executable — add, search, ask, list, show, reindex.

Exactly the six verbs of system/contracts/cli-surface.md; a seventh is a durable
change, not a patch here. Exit codes: 0 success, 1 operation failure, 2 usage or
validation error — the same convention every component answers with, so a verb
that is one component's verb can simply hand its code back. Human output goes to
stdout, progress and diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import components, library
from .home import DEFAULT_HOME, ensure, home_dir

DEFAULT_K = 8

# The derived half of the add pipeline, in derivation order (SPEC-core-002).
# Each step is idempotent on its own, so re-running `add` refreshes the chain
# without redoing the expensive links; `--force` re-derives the transcript too,
# since a re-fetched video deserves a transcript taken from it.
PIPELINE = (("transcribe", "run", True), ("archive", "render", False), ("index", "update", False))

USAGE_ERRORS = (library.NotInLibrary,)
FAILURES = (components.RunError, library.Unreadable, OSError)


def entry_id(reported: str) -> str:
    """The video id ingest just wrote, read back from the entry path it printed.

    ingest owns the mapping from an address to an id; resolving the URL a second
    time here is exactly how the two would come to disagree about where a video
    lives, so the cli asks rather than derives.
    """
    lines = [line.strip() for line in reported.splitlines() if line.strip()]
    video_id = Path(lines[-1]).name if lines else ""
    if not library.VIDEO_ID.fullmatch(video_id):
        raise components.RunError("ingest did not report which library entry it wrote")
    return video_id


def add(home: Path, args) -> int:
    """ingest → transcribe → archive → index, stopping at the first refusal."""
    force = ["--force"] if args.force else []
    code, reported = components.run("ingest", ["add", args.url, *force], home, capture=True)
    if code:
        return code
    video_id = entry_id(reported)
    for module, verb, forcible in PIPELINE:
        step = [verb, video_id, *(force if forcible else [])]
        code, _ = components.run(module, step, home, capture=True)
        if code:
            return code
    print(home / "archive" / f"{video_id}.md")
    return 0


def search(home: Path, args) -> int:
    flags = ["-k", str(args.k), *(["--json"] if args.json else [])]
    # `--` so a query that starts with a dash stays a query all the way down.
    return components.run("index", ["search", *flags, "--", *args.query], home)[0]


def ask(home: Path, args) -> int:
    return components.run("ask", ["answer", "-k", str(args.k), "--", *args.question], home)[0]


def reindex(home: Path, args) -> int:
    return components.run("index", ["reindex"], home)[0]


def show_all(home: Path, args) -> int:
    metas = library.entries(home)
    if args.json:
        print(json.dumps([library.summary(meta) for meta in metas], ensure_ascii=False, indent=2))
    elif metas:
        print(library.listing(metas))
    else:
        print("nothing in the library yet — try `tapedeck add <url>`", file=sys.stderr)
    return 0


def show_one(home: Path, args) -> int:
    meta, paths, missing = library.locate(home, args.video_id)
    if args.json:
        entry = {**meta, "paths": paths, "missing": missing}
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        print(library.detail(meta, paths, missing))
    return 0


VERBS = {
    "add": add,
    "search": search,
    "ask": ask,
    "list": show_all,
    "show": show_one,
    "reindex": reindex,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tapedeck",
        description="A local video brain: download, transcribe, archive, ask.",
        epilog=f"The library lives in $TAPEDECK_HOME (default {DEFAULT_HOME}); "
        "first use creates it, with a config.toml of editable defaults.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    one = sub.add_parser("add", help="ingest, transcribe, archive and index one video")
    one.add_argument("url", help="watch URL, youtu.be/shorts link, or bare video id")
    one.add_argument("--force", action="store_true", help="re-fetch and re-derive it all")

    find = sub.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+")
    find.add_argument("-k", type=int, default=DEFAULT_K, help=f"max results (default {DEFAULT_K})")
    find.add_argument("--json", action="store_true", help="emit the same fields structurally")

    question = sub.add_parser("ask", help="answer a question from the library, with citations")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, default=DEFAULT_K, help="sources to retrieve")

    listing = sub.add_parser("list", help="one line per video: id, date, channel, title")
    listing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    entry = sub.add_parser("show", help="metadata and artifact paths for one video")
    entry.add_argument("video_id", help="the 11-character video id")
    entry.add_argument("--json", action="store_true", help="emit the same fields structurally")

    sub.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)  # argparse exits 2 on a usage error
    try:
        # Resolved and scaffolded before any verb runs: components read config.toml
        # for their seams, and none of them may create the home themselves.
        home = ensure(home_dir())
        return VERBS[args.verb](home, args)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
