"""The tapedeck executable (SPEC-cli-001, system/contracts/cli-surface.md).

Nine verbs and almost no logic. The home is resolved — and scaffolded, if this is
its first use — before any verb runs, then each verb is either handed to the
component that owns it or answered from the library directory itself. Exit codes
are the contract's throughout: 0 success, 1 operation failure, 2 usage error.

The surface is deliberately narrow: a tenth verb is a change to the durable
layer, not to this file.
"""

from __future__ import annotations

import argparse
import sys

from . import components, home, library

DESCRIPTION = "A local video brain: download, transcribe, archive, ask."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tapedeck", description=DESCRIPTION)
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="command")

    add = verbs.add_parser("add", help="fetch, transcribe, archive and index a video, or many")
    add.add_argument(
        "url",
        help="watch URL, youtu.be/shorts link, bare video id, or a playlist or channel URL",
    )
    add.add_argument(
        "--force",
        action="store_true",
        help="re-fetch and re-derive one video that is already here (never a collection)",
    )

    find = verbs.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+")
    find.add_argument("-k", type=int, help="how many results to return")
    find.add_argument("--json", action="store_true", help="emit the same fields structurally")

    question = verbs.add_parser("ask", help="put a question to the librarian of the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help="sources to retrieve (--fast only)")
    question.add_argument("--fast", action="store_true", help="skip the librarian: retrieve, answer")

    catalogue = verbs.add_parser("list", help="one line per video: id, date, channel, title")
    catalogue.add_argument("--json", action="store_true", help="emit the same fields structurally")

    one = verbs.add_parser("show", help="metadata and archive path for one video")
    one.add_argument("video_id")
    one.add_argument("--json", action="store_true", help="emit the same fields structurally")

    verbs.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    gone = verbs.add_parser("rm", help="remove a video everywhere, or just its media")
    gone.add_argument("video_id")
    gone.add_argument(
        "--media-only",
        action="store_true",
        help="delete the video file only, keeping transcript, archive page and index",
    )

    again = verbs.add_parser("retranscribe", help="re-derive every superseded transcript")
    again.add_argument(
        "--dry-run",
        action="store_true",
        help="print the ids that would be redone, one per line, and change nothing",
    )

    verbs.add_parser(
        "adapt-parakeet",
        help="stdin→stdout filter: parakeet-mlx JSON to the whisper shape the seam wants",
    )
    return parser


def limit(k) -> list[str]:
    """`-k` is passed on only when given: the default belongs to the component."""
    return [] if k is None else ["-k", str(k)]


def flag(present: bool, name: str) -> list[str]:
    return [name] if present else []


def dispatch(args, deck) -> int:
    if args.verb == "add":
        return components.add(deck, args.url, args.force)
    if args.verb == "search":
        query = ["search", *args.query, *limit(args.k), *flag(args.json, "--json")]
        return components.delegate("index", query, deck)
    if args.verb == "ask":
        asked = ["answer", *args.question, *limit(args.k), *flag(args.fast, "--fast")]
        return components.delegate("ask", asked, deck)
    if args.verb == "reindex":
        return components.delegate("index", ["reindex"], deck)
    if args.verb == "retranscribe":
        return components.retranscribe(deck, args.dry_run)
    if args.verb == "adapt-parakeet":
        return components.delegate("transcribe", ["from-parakeet"], deck)
    if args.verb == "list":
        return library.show_all(deck, args.json)
    if args.verb == "show":
        return library.show(deck, args.video_id, args.json)
    return library.remove(deck, args.video_id, args.media_only)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)  # unknown verb, bad flags: argparse exits 2
    try:
        return dispatch(args, home.resolve())
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
