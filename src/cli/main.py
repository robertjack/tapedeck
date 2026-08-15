"""The tapedeck surface: the verbs, the global options, and the exit codes.

SPEC-cli-001 and system/contracts/cli-surface.md. The thirteen verbs here are the
whole of it; adding one is a durable-layer change requiring a new clause, so the
parser below is deliberately a flat, boring list rather than anything that could
grow a verb by accident.

Two things happen in a fixed order on every run. `--version` is answered first,
from the installed distribution's own metadata, before any library work at all
(SPEC-cli-006): it is the first thing a stranger runs after installing, and it
must not depend on this machine's layout or on any external tool. Then
`$TAPEDECK_HOME` is resolved and scaffolded, because every remaining verb needs a
home and a first run should not be a chore.

`wiki` is the one verb this parser does not parse. It is a group, and SPEC-cli-009
hands it over whole: everything after the word goes to `python -m wiki` untouched,
including `--help`, so the wiki's own surface has exactly one copy of itself and
a flag it grows tomorrow reaches the installed tapedeck with no code here. The
subparser registered for it exists so `tapedeck --help` lists the verb and
`tapedeck help wiki` has a usage to quote — never to inspect what the user typed.

Exit codes are the contract's: 0 success, 1 the operation failed, 2 the asking
was wrong. Human output goes to stdout, diagnostics and progress to stderr.
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata

import ingest
from transcribe.transcriber import ConfigError as TranscribeConfigError

from . import Failure, Usage, components, doctor, home, pipeline, setup, teach, views

DIST = "tapedeck"
DESCRIPTION = "A local video brain: download, transcribe, archive, ask."
EPILOG = "`tapedeck help` is a tour; `tapedeck help manual` is the whole manual."
WIKI = "wiki"

USAGE_ERRORS = (Usage, ingest.BadRequest, TranscribeConfigError)
FAILURES = (Failure, OSError)
# The two verbs whose whole job is to report on a broken installation. A home
# that cannot be made is one of the things they are for, so they reach their own
# report and say so there rather than dying on the way to it.
DIAGNOSTIC = ("doctor", "setup")


def build_parser() -> tuple[argparse.ArgumentParser, dict]:
    """The parser, and the subparsers by name so `help <verb>` can quote them."""
    parser = argparse.ArgumentParser(prog=DIST, description=DESCRIPTION, epilog=EPILOG)
    parser.add_argument(
        "--version", action="store_true", help="print the installed version and exit"
    )
    subs = parser.add_subparsers(dest="verb", metavar="<verb>")
    verbs: dict[str, argparse.ArgumentParser] = {}

    def verb(name: str, blurb: str) -> argparse.ArgumentParser:
        verbs[name] = subs.add_parser(name, help=blurb, description=blurb)
        return verbs[name]

    adding = verb("add", "fetch, transcribe, archive and index a video, playlist or channel")
    adding.add_argument("url", help="a video URL or id, or a playlist or channel URL")
    adding.add_argument("--force", action="store_true", help="re-fetch one video from scratch")

    finding = verb("search", "ranked timestamped excerpts with deep links")
    finding.add_argument("query", nargs="+")
    finding.add_argument("-k", type=int, help="max results (default 8)")
    finding.add_argument("--json", action="store_true", help="emit the same fields structurally")

    asking = verb("ask", "a cited answer from the library")
    asking.add_argument("question", nargs="+")
    asking.add_argument("-k", type=int, help="sources to retrieve (--fast only)")
    asking.add_argument("--fast", action="store_true", help="strict retrieval instead of the agent")
    asking.add_argument("--video", help="answer from this library video alone")

    browsing = verb("list", "one line per video: id, date, channel, title")
    browsing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    showing = verb("show", "metadata and the archive page for one video")
    showing.add_argument("video_id", metavar="id")
    showing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    verb("reindex", "rebuild tapedeck.db from archive/ alone")

    removing = verb("rm", "remove a video everywhere, or reclaim just its disk")
    removing.add_argument("video_id", metavar="id")
    removing.add_argument(
        "--media-only", action="store_true", help="delete the video file, keep the knowledge"
    )

    redoing = verb("retranscribe", "re-derive every transcript a newer model has superseded")
    redoing.add_argument("--dry-run", action="store_true", help="list what would be redone")

    routing = verb(WIKI, "the prose layer: file, sync, lint or rebuild the wiki")
    routing.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        metavar="...",
        help="handed to the wiki component untouched — `tapedeck wiki --help` is its own usage",
    )

    verb("adapt-parakeet", "stdin to stdout: parakeet JSON into the whisper shape")

    checking = verb("doctor", "check the seams, the tools and this machine; change nothing")
    checking.add_argument("--json", action="store_true", help="emit the same checks structurally")

    starting = verb("setup", "first run: scaffold the home, check it, and name what would fix it")
    starting.add_argument(
        "--yes", action="store_true", help="run the printed commands, then check again"
    )

    teaching = verb("help", "a tour, a verb's usage and example, or the full manual")
    teaching.add_argument("topic", nargs="?", metavar="<verb>|manual")

    return parser, verbs


def report_version() -> int:
    """The installed version, from the distribution's metadata — `pyproject.toml`
    is the single source of truth and no string here duplicates it. A build whose
    own metadata cannot be read is broken, and says so rather than inventing a
    number for a user to report in a bug."""
    try:
        print(f"{DIST} {metadata.version(DIST)}")
    except metadata.PackageNotFoundError:
        print(
            f"error: {DIST} cannot read its own package metadata, so it cannot say "
            "what version it is — this install is broken; reinstall it",
            file=sys.stderr,
        )
        return 1
    return 0


def dispatch(args, deck, verbs) -> int:
    if args.verb == "add":
        return pipeline.add(deck, args.url, args.force)
    if args.verb == "search":
        return views.search(deck, args.query, args.k, args.json)
    if args.verb == "ask":
        return views.ask(deck, args.question, args.k, args.fast, args.video)
    if args.verb == "list":
        return views.listing(deck, args.json)
    if args.verb == "show":
        return views.show(deck, args.video_id, args.json)
    if args.verb == "reindex":
        return views.reindex(deck)
    if args.verb == "rm":
        return views.remove(deck, args.video_id, args.media_only)
    if args.verb == "retranscribe":
        return pipeline.retranscribe(deck, args.dry_run)
    if args.verb == WIKI:  # only reachable if the routing above ever stops firing
        return components.passthrough(WIKI, args.args, deck)
    if args.verb == "adapt-parakeet":
        # transcribe owns the filter; the cli only puts it on the installed
        # surface, so the published parakeet seam works wherever tapedeck does
        # and needs no assumption about which python is on PATH.
        return components.passthrough("transcribe", ["from-parakeet"], deck)
    if args.verb == "doctor":
        return doctor.run(deck, args.json)
    if args.verb == "setup":
        return setup.run(deck, args.yes)
    return teach.teach(args.topic, verbs)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser, verbs = build_parser()

    if argv[:1] == [WIKI]:
        # Routed before parsing, so nothing here reads, validates, reorders or
        # rewords a single word of the wiki's surface (SPEC-cli-009).
        try:
            deck = prepared(WIKI)
        except OSError as exc:
            return _report(exc, 1)
        return components.passthrough(WIKI, argv[1:], deck)

    args = parser.parse_args(argv)
    if args.version:
        return report_version()
    if args.verb is None:
        parser.print_usage(sys.stderr)
        print("error: a verb is required — `tapedeck help` for a tour", file=sys.stderr)
        return 2

    try:
        return dispatch(args, prepared(args.verb), verbs)
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except FAILURES as exc:
        return _report(exc, 1)


def prepared(verb: str):
    """The resolved home, scaffolded — the first-run courtesy every verb performs
    and none of them repeats."""
    deck = home.resolve()
    try:
        home.scaffold(deck)
    except OSError as exc:
        if verb not in DIAGNOSTIC:
            raise
        print(f"warning: could not prepare {deck} — {exc}", file=sys.stderr)
    return deck


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
