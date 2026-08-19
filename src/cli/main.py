"""The `tapedeck` executable's argument parsing and dispatch (SPEC-cli-001).

`--version`, `wiki`, and the internal wiki-filing worker are intercepted
before argparse ever runs: `--version` must resolve no library home at all
(SPEC-cli-006), and `wiki` is handed to `python -m wiki` whole, with none of
its own sub-verbs or flags re-declared here (SPEC-cli-009, LESSON-0003) — a
bare `wiki` entry is still registered below so it is listed in `--help`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import doctor, pipeline, teach
from . import setup as setup_mod
from .components import WORKER_ARG, run_passthrough, wiki_worker_main
from .home import ensure_home, home_dir

DIST_NAME = "tapedeck-cli"


def _subparser_choices(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tapedeck", description="A local video brain.")
    verbs = parser.add_subparsers(dest="verb", required=True)

    adding = verbs.add_parser(
        "add", help="ingest, transcribe, archive, and index a video or collection"
    )
    adding.add_argument("url", help="a video URL/id, or a playlist/channel URL")
    adding.add_argument(
        "--force", action="store_true", help="re-fetch a video already here (single video only)"
    )
    adding.add_argument("--verbose", action="store_true", help="stream the fetcher raw")

    searching = verbs.add_parser("search", help="ranked timestamped excerpts with deep links")
    searching.add_argument("query", nargs="+")
    searching.add_argument("-k", type=int, default=8, help="max results (default 8)")
    searching.add_argument("--json", action="store_true")

    asking = verbs.add_parser("ask", help="answer a question from your library, cited")
    asking.add_argument("question", nargs="+")
    asking.add_argument("-k", type=int, help="sources to retrieve (--fast mode)")
    asking.add_argument("--fast", action="store_true", help="strict retrieval pipeline")
    asking.add_argument("--video", help="answer from this library video alone")

    listing = verbs.add_parser("list", help="one line per video: id, date, channel, title")
    listing.add_argument("--json", action="store_true")

    showing = verbs.add_parser("show", help="metadata and archive path for one video")
    showing.add_argument("video_id")
    showing.add_argument("--json", action="store_true")

    verbs.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    removing = verbs.add_parser("rm", help="remove a video everywhere, or just its media")
    removing.add_argument("video_id")
    removing.add_argument("--media-only", action="store_true")

    retr = verbs.add_parser(
        "retranscribe", help="re-derive transcripts superseded by a model change"
    )
    retr.add_argument("--dry-run", action="store_true")

    verbs.add_parser("wiki", help="file, sync, lint, rebuild, or tend the wiki")

    verbs.add_parser(
        "adapt-parakeet", help="stdin/stdout filter: parakeet-mlx JSON to the whisper shape"
    )

    doct = verbs.add_parser("doctor", help="diagnose this installation; changes nothing")
    doct.add_argument("--json", action="store_true")

    setup_p = verbs.add_parser(
        "setup", help="first-run wizard: scaffold, diagnose, and offer remedies"
    )
    setup_p.add_argument("--yes", action="store_true")
    setup_p.add_argument("--refresh", action="store_true")

    helping = verbs.add_parser("help", help="a one-screen tour, per-verb usage, or the manual")
    helping.add_argument("topic", nargs="?")

    return parser


def _version() -> int:
    from importlib.metadata import PackageNotFoundError, version

    try:
        v = version(DIST_NAME)
    except PackageNotFoundError as exc:
        print(
            f"error: {DIST_NAME} is not installed with readable metadata — {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"tapedeck {v}")
    return 0


def _adapt_parakeet() -> int:
    import transcribe

    try:
        result = transcribe.adapt(sys.stdin.read())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)

    if argv and argv[0] == "--version":
        return _version()
    if argv and argv[0] == "wiki":
        return run_passthrough(ensure_home(home_dir()), "wiki", argv[1:])
    if argv and argv[0] == WORKER_ARG:
        wiki_worker_main(home_dir(), argv[1:])
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)
    home = ensure_home(home_dir())

    if args.verb == "add":
        return pipeline.add(home, args.url, args.force, args.verbose)
    if args.verb == "search":
        out = ["search", *args.query, "-k", str(args.k)]
        if args.json:
            out.append("--json")
        return run_passthrough(home, "index", out)
    if args.verb == "ask":
        out = ["run", *args.question]
        if args.k is not None:
            out += ["-k", str(args.k)]
        if args.fast:
            out.append("--fast")
        if args.video:
            out += ["--video", args.video]
        return run_passthrough(home, "ask", out)
    if args.verb == "list":
        return pipeline.list_videos(home, args.json)
    if args.verb == "show":
        return pipeline.show(home, args.video_id, args.json)
    if args.verb == "reindex":
        return run_passthrough(home, "index", ["reindex"])
    if args.verb == "rm":
        return pipeline.rm(home, args.video_id, args.media_only)
    if args.verb == "retranscribe":
        return pipeline.retranscribe(home, args.dry_run)
    if args.verb == "adapt-parakeet":
        return _adapt_parakeet()
    if args.verb == "doctor":
        return doctor.run(home, args.json)
    if args.verb == "setup":
        return setup_mod.run(home, args.yes, args.refresh)
    # args.verb == "help": the only verb left once every other branch has returned.
    if args.topic is None:
        return teach.tour()
    return teach.verb(_subparser_choices(parser), args.topic)


if __name__ == "__main__":
    sys.exit(main())
