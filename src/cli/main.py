"""The `tapedeck` executable: the verbs of system/contracts/cli-surface.md.

Exactly ten verbs, because the surface is a contract and a new one is a durable
change, not a convenience (SPEC-cli-001). Human output goes to stdout, progress
and diagnostics to stderr, and every verb returns one of three codes: 0 done,
1 the operation failed, 2 the request was malformed.

The shape of every run is the same three moves — parse, resolve the home (making
one if this is the first time), then hand the work to whoever owns it. What the
cli decides is which component to ask and in what order; what it never decides is
whether an id is well-formed, whether a video is present, or what a transcript's
model label means, because each of those belongs to a component that would
otherwise be contradicted (LESSON-0003).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ingest import sources
from transcribe import transcriber

from . import Failure, components, home as home_module, pipeline, teach, views

PROG = "tapedeck"
USAGE_ERRORS = (sources.BadRequest, transcriber.ConfigError)


def build() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="A local video brain: download, transcribe, archive, ask.",
        epilog="`tapedeck help` teaches the whole tool in one screen.",
    )
    verbs = parser.add_subparsers(dest="verb", metavar="<verb>")

    fetch = verbs.add_parser(
        "add", help="fetch, transcribe, archive and index a video or collection"
    )
    fetch.add_argument("url", help="a video URL or id, or a playlist or channel URL")
    fetch.add_argument(
        "--force",
        action="store_true",
        help="re-fetch a video already in the library (one video at a time)",
    )

    find = verbs.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+", help="the words to look for")
    find.add_argument("-k", type=int, help="how many results at most (default 8)")
    find.add_argument("--json", action="store_true", help="the same fields, structurally")

    question = verbs.add_parser("ask", help="a cited answer from the library")
    question.add_argument("question", nargs="+", help="what you want to know")
    question.add_argument("-k", type=int, help="sources to retrieve (--fast only)")
    question.add_argument(
        "--fast", action="store_true", help="the strict retrieval pipeline instead of the librarian"
    )
    question.add_argument("--video", help="answer from this one library video")

    catalogue = verbs.add_parser("list", help="one line per video: id, date, channel, title")
    catalogue.add_argument("--json", action="store_true", help="the same fields, structurally")

    one = verbs.add_parser("show", help="metadata and the archive path for one video")
    one.add_argument("video_id", help="an 11-character video id")
    one.add_argument("--json", action="store_true", help="the same fields, structurally")

    verbs.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    drop = verbs.add_parser("rm", help="remove a video, or just reclaim its disk")
    drop.add_argument("video_id", help="an 11-character video id")
    drop.add_argument(
        "--media-only",
        action="store_true",
        help="delete the video file(s) only — transcript, page and index stay",
    )

    again = verbs.add_parser(
        "retranscribe", help="re-derive every transcript a better model supersedes"
    )
    again.add_argument(
        "--dry-run", action="store_true", help="print the ids that would be redone; change nothing"
    )

    verbs.add_parser(
        "adapt-parakeet", help="stdin to stdout: parakeet JSON in the whisper shape"
    )

    teaching = verbs.add_parser("help", help="the tour, a verb's usage and example, or the manual")
    teaching.add_argument("topic", nargs="?", help="a verb, or `manual`")
    return parser, verbs


def _option(name: str, value) -> list[str]:
    return [name, str(value)] if value is not None else []


def _switch(name: str, on: bool) -> list[str]:
    return [name] if on else []


def dispatch(args, home: Path, choices) -> int:
    verb = args.verb
    if verb is None:
        # `tapedeck` alone is someone looking for the way in, not a usage error.
        return teach.teach(choices, None)
    if verb == "help":
        return teach.teach(choices, args.topic)
    if verb == "add":
        return pipeline.add(home, args.url, args.force)
    if verb == "list":
        return views.listing(home, args.json)
    if verb == "show":
        return views.show(home, args.video_id, args.json)
    if verb == "rm":
        return pipeline.remove(home, args.video_id, args.media_only)
    if verb == "retranscribe":
        return pipeline.retranscribe(home, args.dry_run)
    if verb == "search":
        # `--` so a query that starts with a dash is words, not flags.
        return components.forward(
            components.INDEX,
            ["search", *_option("-k", args.k), *_switch("--json", args.json), "--", *args.query],
            home,
        )
    if verb == "ask":
        return components.forward(
            components.ASK,
            [
                "run",
                *_option("-k", args.k),
                *_switch("--fast", args.fast),
                *_option("--video", args.video),
                "--",
                *args.question,
            ],
            home,
        )
    if verb == "reindex":
        return components.forward(components.INDEX, ["reindex"], home)
    # adapt-parakeet: transcribe's filter, on the installed surface so the
    # published parakeet seam works without assuming a python on PATH. stdin and
    # stdout are the component's; the cli touches neither.
    return components.forward(components.TRANSCRIBE, ["from-parakeet"], home)


def main(argv=None) -> int:
    parser, verbs = build()
    args = parser.parse_args(argv)
    try:
        home = home_module.prepare(home_module.resolve())
        return dispatch(args, home, verbs.choices)
    except BrokenPipeError:
        return 0  # `tapedeck help manual | head` is not a failed command
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except Failure as exc:
        return _report(exc, exc.code)
    except OSError as exc:
        return _report(exc, 1)


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
