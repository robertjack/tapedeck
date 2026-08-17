"""The `tapedeck` entrypoint (SPEC-cli-001): argument parsing, home
resolution, and dispatch to the other components — never re-deriving their
vocabulary, only routing to it.
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata

from . import components
from . import doctor as doctor_module
from . import home as home_module
from . import pipeline
from . import setup as setup_module
from . import teach
from . import views

PROG = "tapedeck"


def build_parser() -> tuple[argparse.ArgumentParser, dict]:
    parser = argparse.ArgumentParser(
        prog=PROG, description="A local video brain: download, transcribe, archive, ask."
    )
    parser.add_argument(
        "--version", action="store_true", help="print the installed version and exit"
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    subparsers: dict = {}

    p = sub.add_parser(
        "add", help="ingest, transcribe, archive and index one video, or sweep a collection"
    )
    p.add_argument("url", help="a video URL/id, or a playlist/channel URL")
    p.add_argument("--force", action="store_true", help="re-fetch a single video from scratch")
    subparsers["add"] = p

    p = sub.add_parser("search", help="ranked timestamped excerpts with deep links")
    p.add_argument("query", nargs="+")
    p.add_argument("-k", type=int, default=8, help="max results (default 8)")
    p.add_argument("--json", action="store_true", help="emit the same fields structurally")
    subparsers["search"] = p

    p = sub.add_parser("ask", help="answer a question from the library, with cited sources")
    p.add_argument("question", nargs="+")
    p.add_argument("-k", type=int, default=None, help="sources to retrieve in --fast mode")
    p.add_argument("--fast", action="store_true", help="retrieve, then answer (no agent)")
    p.add_argument("--video", help="answer from this one video alone")
    subparsers["ask"] = p

    p = sub.add_parser("list", help="one line per video: id, date, channel, title")
    p.add_argument("--json", action="store_true")
    subparsers["list"] = p

    p = sub.add_parser("show", help="metadata and archive path for one video")
    p.add_argument("video_id")
    p.add_argument("--json", action="store_true")
    subparsers["show"] = p

    p = sub.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")
    subparsers["reindex"] = p

    p = sub.add_parser("rm", help="remove a video, or just reclaim its media")
    p.add_argument("video_id")
    p.add_argument(
        "--media-only", action="store_true", help="keep metadata/transcript/archive/index"
    )
    subparsers["rm"] = p

    p = sub.add_parser(
        "retranscribe", help="re-derive transcripts superseded by the configured model"
    )
    p.add_argument("--dry-run", action="store_true")
    subparsers["retranscribe"] = p

    p = sub.add_parser(
        "wiki", help="the prose layer: file, sync, lint, rebuild, tend (routed to python -m wiki)"
    )
    subparsers["wiki"] = p

    p = sub.add_parser("adapt-parakeet", help="stdin/stdout filter: parakeet JSON to whisper shape")
    subparsers["adapt-parakeet"] = p

    p = sub.add_parser("doctor", help="diagnose this installation; changes nothing")
    p.add_argument("--json", action="store_true")
    subparsers["doctor"] = p

    p = sub.add_parser("setup", help="first-run wizard: scaffold, check, print remedies")
    p.add_argument("--yes", action="store_true", help="run the printed remedies")
    subparsers["setup"] = p

    p = sub.add_parser("help", help="a one-screen tour, per-verb help, or the full manual")
    p.add_argument("topic", nargs="?")
    subparsers["help"] = p

    return parser, subparsers


def cmd_version() -> int:
    try:
        version = metadata.version("tapedeck")
    except metadata.PackageNotFoundError as exc:
        print(f"error: tapedeck's package metadata could not be read — {exc}", file=sys.stderr)
        return 1
    print(version)
    return 0


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)

    # --version is answered before any library work (SPEC-cli-006).
    if raw[:1] == ["--version"]:
        return cmd_version()

    # `wiki` is handed over whole (SPEC-cli-009): everything after it goes to
    # `python -m wiki` untouched, including its own `-h`/`--help`, which is
    # why this bypasses argparse entirely rather than routing through a
    # subparser that would try to interpret those tokens itself.
    if raw[:1] == ["wiki"]:
        home = home_module.home_dir()
        home_module.ensure_home(home)
        return components.run_passthrough("wiki", raw[1:], home)

    parser, subparsers = build_parser()
    args = parser.parse_args(raw)
    if args.version:
        return cmd_version()

    home = home_module.home_dir()
    home_module.ensure_home(home)

    if args.verb == "add":
        return pipeline.cmd_add(args, home)
    if args.verb == "search":
        search_args = ["search", *args.query, "-k", str(args.k)]
        if args.json:
            search_args.append("--json")
        return components.run_passthrough("index", search_args, home)
    if args.verb == "ask":
        ask_args = ["run", *args.question]
        if args.k is not None:
            ask_args += ["-k", str(args.k)]
        if args.fast:
            ask_args.append("--fast")
        if args.video:
            ask_args += ["--video", args.video]
        return components.run_passthrough("ask", ask_args, home)
    if args.verb == "list":
        return views.cmd_list(args, home)
    if args.verb == "show":
        return views.cmd_show(args, home)
    if args.verb == "reindex":
        return components.run_passthrough("index", ["reindex"], home)
    if args.verb == "rm":
        return pipeline.cmd_rm(args, home)
    if args.verb == "retranscribe":
        return pipeline.cmd_retranscribe(args, home)
    if args.verb == "adapt-parakeet":
        return components.run_passthrough("transcribe", ["from-parakeet"], home)
    if args.verb == "doctor":
        return doctor_module.cmd_doctor(args, home)
    if args.verb == "setup":
        return setup_module.cmd_setup(args, home)
    if args.verb == "help":
        return teach.cmd_help(args, home, subparsers)

    parser.error(f"unknown verb {args.verb!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
