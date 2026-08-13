"""Component boundary: `python -m ask run <question> [-k N] [--fast] [--video <id>]`.

Reads config.toml, the library's metadata and the index's database, and writes
nothing — ask owns no path in system/contracts/library-layout.md. Exit codes follow
system/contracts/cli-surface.md: 0 success, 1 operation failure, 2 usage or config
error; the answer goes to stdout, everything else to stderr.

Both modes are the same shape, and the order below is the whole design: settle
everything deterministic first, then think, then check what came back. Nothing
probabilistic runs until the library is known to have something to say — and, in
fast mode, until the index it would say it from is one this build can read — and no
answer reaches stdout before its citations have been checked against the library.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import citations, retrieve, seams
from .library import Library

DEFAULT_HOME = "~/dev/storage/tapedeck"
DEFAULT_K = 8
NO_SOURCES = "no sources in the library"

USAGE_ERRORS = (seams.ConfigError,)
FAILURES = (seams.AnswerError, retrieve.IndexUnreadable, OSError)


class Failure(RuntimeError):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def scope_for(library: Library, video_id: str | None) -> str | None:
    """Settle `--video` first: a scope that names nothing here is a mistake in the
    asking, and no model should be spent on it (SPEC-ask-003)."""
    if video_id is None or library.holds(video_id):
        return video_id
    raise Failure(f"no video {video_id!r} in the library — try `tapedeck list`", code=2)


def librarian(home: Path, library: Library, question: str, scope: str | None) -> int:
    """Turn the agent loose in the library, then audit what it comes back with."""
    command = seams.command(home, seams.LIBRARIAN_KEY, "librarian")
    seams.brief(home)
    if not library.stocked():
        raise Failure(f"{NO_SOURCES} — `tapedeck add <url>` starts one")

    answer = seams.run(command, home, citations.ask_for(question, scope), "librarian", cwd=home)
    links = citations.deep_links(answer)
    if not links:
        raise Failure(
            "the librarian answered without a citation — an answer tapedeck cannot "
            "trace to a moment in the library is not one it prints"
        )
    problems = citations.unverified(links, library, scope)
    if problems:
        raise Failure("refusing a fabricated citation:\n  " + "\n  ".join(problems))
    print(answer)
    return 0


def fast(home: Path, question: str, k: int, scope: str | None) -> int:
    """Retrieve, then answer from the retrieval alone, then number it back."""
    command = seams.command(home, seams.ANSWERER_KEY, "answerer")
    sources = retrieve.top_k(home, question, k, scope)
    if not sources:
        where = f" (in {scope})" if scope else ""
        raise Failure(f"{NO_SOURCES} for this question{where}")

    answer = seams.run(command, home, citations.prompt(question, sources), "answerer")
    stray = citations.invented(answer, len(sources))
    if stray:
        cited = ", ".join(f"[{number}]" for number in stray)
        raise Failure(
            f"the answerer cited {cited}, which no retrieved source carries "
            f"({len(sources)} were given) — refusing an invented citation"
        )
    print(citations.document(answer, sources))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ask", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    # One verb, two names: `run` is the boundary the evals drive, `answer` the name
    # the cli calls it by. Either rename breaks a caller ask does not own.
    question = sub.add_parser("run", aliases=["answer"], help="answer from the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help=f"sources to retrieve (default {DEFAULT_K})")
    question.add_argument("--fast", action="store_true", help="retrieve, then answer")
    question.add_argument("--video", help="answer from this library video alone")
    args = parser.parse_args(argv)

    try:
        if args.k is not None and args.k < 1:
            raise Failure(f"-k must be at least 1 (got {args.k})", code=2)
        home, asked = home_dir(), " ".join(args.question)
        library = Library(home)
        scope = scope_for(library, args.video)
        if args.fast:
            return fast(home, asked, DEFAULT_K if args.k is None else args.k, scope)
        if args.k is not None:
            # -k sizes a retrieval the librarian does not do; say so rather than let
            # the flag look as though it changed the answer.
            print("note: -k applies to --fast retrieval only", file=sys.stderr)
        return librarian(home, library, asked, scope)
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except FAILURES as exc:
        return _report(exc, 1)
    except Failure as exc:
        return _report(exc, exc.code)


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
