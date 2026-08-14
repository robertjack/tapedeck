"""The `tapedeck` surface: nine verbs, three exit codes, one home.

The verbs are exactly system/contracts/cli-surface.md's — adding one is a durable
change, not a convenience (SPEC-cli-001). Read-only verbs that a component
already implements are handed straight to it, streams and exit code and all; the
verbs that orchestrate several components live in `pipeline` and `views`.

Exit codes: 0 done, 1 the operation failed, 2 the request could not be acted on.
The mapping is the whole of the error handling here — a bad URL and a
misconfigured seam are the user's to fix (2), a fetch or a render that fell over
is the run's failure (1). Answers go to stdout, everything else to stderr.
"""

from __future__ import annotations

import argparse
import sys

import ingest
from transcribe.transcriber import ConfigError as TranscriberConfigError

from . import pipeline, views
from .components import Failed, Usage, passthrough
from .home import home_dir, scaffold

DESCRIPTION = "A local video brain: download, transcribe, archive, ask."
USAGE_ERRORS = (Usage, ingest.BadRequest, TranscriberConfigError)
FAILURES = (Failed, OSError)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tapedeck", description=DESCRIPTION)
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="<verb>")

    adding = verbs.add_parser("add", help="fetch, transcribe, archive and index a video or a whole collection")
    adding.add_argument("url", help="a video URL or id, or a playlist or channel URL")
    adding.add_argument(
        "--force",
        action="store_true",
        help="re-fetch a video that is already here, and re-derive from it (one video, never a collection)",
    )

    finding = verbs.add_parser("search", help="ranked timestamped excerpts with deep links")
    finding.add_argument("query", nargs="+", help="what to look for")
    finding.add_argument("-k", type=int, help="how many results to print")
    finding.add_argument("--json", action="store_true", help="emit the same fields structurally")

    asking = verbs.add_parser("ask", help="answer a question from the library, with citations")
    asking.add_argument("question", nargs="+", help="the question")
    asking.add_argument("-k", type=int, help="sources to retrieve (--fast only)")
    asking.add_argument("--fast", action="store_true", help="strict retrieval pipeline instead of the librarian")
    asking.add_argument("--video", help="answer from this video alone")

    listing = verbs.add_parser("list", help="one line per video: id, date, channel, title")
    listing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    showing = verbs.add_parser("show", help="metadata and archive path for one video")
    showing.add_argument("video_id", help="an 11-character video id")
    showing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    verbs.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    removing = verbs.add_parser("rm", help="remove a video everywhere, or reclaim just its disk")
    removing.add_argument("video_id", help="an 11-character video id")
    removing.add_argument(
        "--media-only",
        action="store_true",
        help="delete the video file(s) only — transcript, archive page and index stay",
    )

    redoing = verbs.add_parser(
        "retranscribe", help="re-derive every transcript whose model label is out of date"
    )
    redoing.add_argument(
        "--dry-run", action="store_true", help="print the ids that would be redone and change nothing"
    )

    verbs.add_parser(
        "adapt-parakeet", help="stdin to stdout: parakeet-mlx JSON in the whisper shape"
    )
    return parser


def _k(value: int | None) -> list[str]:
    """Pass `-k` on only when asked. A default repeated here would be a second
    opinion about a number the component already has one about."""
    return [] if value is None else ["-k", str(value)]


def dispatch(args, home) -> int:
    if args.verb == "add":
        return pipeline.add(home, args.url, args.force)
    if args.verb == "search":
        flags = [*_k(args.k), *(["--json"] if args.json else [])]
        # `--` first: a question or query that starts with a dash is text, not a flag.
        return passthrough(home, "index", ["search", *flags, "--", *args.query])
    if args.verb == "ask":
        flags = [
            *_k(args.k),
            *(["--fast"] if args.fast else []),
            *(["--video", args.video] if args.video else []),
        ]
        return passthrough(home, "ask", ["run", *flags, "--", *args.question])
    if args.verb == "list":
        return views.list_videos(home, args.json)
    if args.verb == "show":
        return views.show(home, args.video_id, args.json)
    if args.verb == "reindex":
        return passthrough(home, "index", ["reindex"])
    if args.verb == "rm":
        return views.remove(home, args.video_id, args.media_only)
    if args.verb == "retranscribe":
        return pipeline.retranscribe(home, args.dry_run)
    return passthrough(home, "transcribe", ["from-parakeet"])


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # The home is resolved and made real before any verb runs: every one of
        # them reads config.toml, directly or through a component (SPEC-cli-001).
        home = scaffold(home_dir())
        return dispatch(args, home)
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except FAILURES as exc:
        return _report(exc, 1)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 1


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
