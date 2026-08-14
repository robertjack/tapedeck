"""The `tapedeck` executable: the surface, and the dispatch behind it.

The verbs are exactly the ones in system/contracts/cli-surface.md and adding one
is a durable-layer change (SPEC-cli-001). Exit codes are that contract's — 0
done, 1 the operation failed, 2 the request was malformed — and a code that came
back from a component is passed on rather than re-decided here: the component
that did the work knows better than its caller whether a failure was the user's.

Order matters in `main`. `--version` is answered before anything touches the
disk (SPEC-cli-006), teaching needs no library either, and only a verb that
really reads or writes the library resolves and scaffolds the home.
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

from ingest import BadRequest

from . import FAILURE, USAGE, Failure, components, home, pipeline, teach, views

PROG = "tapedeck"
DISTRIBUTION = "tapedeck"
DESCRIPTION = "A local video brain: download, transcribe, archive, ask."
EPILOG = "`tapedeck help` is a one-screen tour; `tapedeck help manual` is the manual."
DEFAULT_K = 8


def build_parser() -> tuple[argparse.ArgumentParser, dict]:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed version and exit, touching no library",
    )
    verbs = parser.add_subparsers(dest="verb", metavar="<verb>")

    fetching = verbs.add_parser("add", help="fetch, transcribe, archive and index a video")
    fetching.add_argument("url", help="a video URL or id, or a playlist/channel URL")
    fetching.add_argument(
        "--force", action="store_true", help="re-fetch one video that is already here"
    )

    finding = verbs.add_parser("search", help="ranked timestamped excerpts with deep links")
    finding.add_argument("query", nargs="+", help="the words to look for")
    finding.add_argument("-k", type=int, help=f"max results (default {DEFAULT_K})")
    finding.add_argument("--json", action="store_true", help="emit the same fields structurally")

    asking = verbs.add_parser("ask", help="an answer from the library, with checked citations")
    asking.add_argument("question", nargs="+", help="what you want to know")
    asking.add_argument("-k", type=int, help=f"sources to retrieve, --fast only (default {DEFAULT_K})")
    asking.add_argument("--fast", action="store_true", help="strict retrieval instead of the librarian")
    asking.add_argument("--video", metavar="<id>", help="answer from this video alone")

    listing = verbs.add_parser("list", help="one line per video: id, date, channel, title")
    listing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    showing = verbs.add_parser("show", help="metadata and the archive page for one video")
    showing.add_argument("video_id", metavar="<id>", help="an 11-character video id")
    showing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    verbs.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    removing = verbs.add_parser("rm", help="remove a video, or just reclaim its disk")
    removing.add_argument("video_id", metavar="<id>", help="an 11-character video id")
    removing.add_argument(
        "--media-only",
        action="store_true",
        help="delete the video file(s) only, keeping transcript, page and index",
    )

    redoing = verbs.add_parser(
        "retranscribe", help="re-derive every transcript a better model has superseded"
    )
    redoing.add_argument(
        "--dry-run", action="store_true", help="print the ids that would be redone; change nothing"
    )

    verbs.add_parser(
        "adapt-parakeet", help="stdin to stdout: parakeet JSON in the whisper shape"
    )

    teaching = verbs.add_parser("help", help="the tour, one verb's usage, or the full manual")
    teaching.add_argument(
        "topic", nargs="?", metavar="<verb>|manual", help="what you want taught"
    )
    return parser, dict(verbs.choices)


def show_version(out=None) -> int:
    """The installed distribution's own metadata, and nothing else.

    pyproject.toml is the single source of truth (SPEC-cli-006), so there is no
    constant here to fall back on: a build whose metadata cannot be read is a
    broken install, and saying so is more use than a number we made up.
    """
    out = sys.stdout if out is None else out
    try:
        number = installed_version(DISTRIBUTION)
    except PackageNotFoundError as exc:
        raise Failure(
            f"this {PROG} is not an installed distribution, so it has no version "
            f"to report ({exc}) — reinstall it",
            code=FAILURE,
        ) from exc
    print(f"{PROG} {number}", file=out)
    return 0


def _passthrough(flags: list[str], text: str) -> list[str]:
    """Flags, then `--`, then the words — so a question or query that starts with
    a dash reaches the component as text rather than as an unknown option."""
    return [*flags, "--", text]


def dispatch(args, verbs: dict) -> int:
    if args.verb == "help":
        return teach.teach(verbs, args.topic)
    if args.verb == "adapt-parakeet":
        # A filter, not a library verb: stdin to stdout, exit code passed
        # through, and no home is created just to run it.
        return components.run("transcribe", ["from-parakeet"], home.resolve())

    where = home.prepare()
    if args.verb == "add":
        return pipeline.add(where, args.url, args.force)
    if args.verb == "search":
        flags = ([] if args.k is None else ["-k", str(args.k)]) + (["--json"] if args.json else [])
        return components.run("index", ["search", *_passthrough(flags, " ".join(args.query))], where)
    if args.verb == "ask":
        flags = ([] if args.k is None else ["-k", str(args.k)]) + (["--fast"] if args.fast else [])
        flags += [] if args.video is None else ["--video", args.video]
        return components.run("ask", ["run", *_passthrough(flags, " ".join(args.question))], where)
    if args.verb == "list":
        return views.listing(where, args.json)
    if args.verb == "show":
        return views.show(where, args.video_id, args.json)
    if args.verb == "reindex":
        return components.run("index", ["reindex"], where)
    if args.verb == "rm":
        return pipeline.remove(where, args.video_id, args.media_only)
    return pipeline.retranscribe(where, args.dry_run)


def main(argv=None) -> int:
    parser, verbs = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.version:
            return show_version()
        if args.verb is None:
            # Someone typed the name of the tool to find out what it is.
            return teach.tour()
        return dispatch(args, verbs)
    except Failure as exc:
        return _report(exc, exc.code)
    except BadRequest as exc:
        # ingest owns what a URL means, including that this one means nothing.
        return _report(exc, USAGE)
    except OSError as exc:
        return _report(exc, FAILURE)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return FAILURE


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
