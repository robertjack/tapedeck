"""Component boundary: `python -m ask run <question> [-k N] [--fast]` (alias: `answer`).

Reads config.toml, the library's metadata and the index's database, and writes
nothing anywhere — ask owns no path in system/contracts/library-layout.md. Exit
codes follow system/contracts/cli-surface.md: 0 success, 1 operation failure, 2
usage or configuration error. The answer goes to stdout, everything else to stderr.

The two modes are the same shape, and the order below is the whole design: settle
everything deterministic first, then think, then check what came back. Nothing
probabilistic runs until the library has been shown to have something to say — a
model with no sources would answer from itself — and no answer reaches stdout
before its citations have been checked against the library.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import citations, library, retrieve, seams

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


def librarian(home: Path, question: str) -> int:
    """Turn the agent loose in the library, then audit what it comes back with."""
    command = seams.command(home, seams.LIBRARIAN_KEY, "librarian")
    seams.brief(home)
    videos = library.videos(home)
    if not videos:
        raise Failure(f"{NO_SOURCES} — `tapedeck add <url>` starts one")

    answer = seams.run(command, home, f"{question}\n", "librarian", cwd=home)
    links = citations.deep_links(answer)
    if not links:
        raise Failure(
            "the librarian answered without a single citation — an answer tapedeck "
            "cannot trace back to a moment in the library is not an answer it prints"
        )
    problems = citations.unverified(links, videos)
    if problems:
        raise Failure(
            "the librarian cited what the library does not have — refusing a "
            "fabricated citation:\n  " + "\n  ".join(problems)
        )
    print(answer)
    return 0


def fast(home: Path, question: str, k: int) -> int:
    """Retrieve, then answer from the retrieval alone, then number it back."""
    command = seams.command(home, seams.ANSWERER_KEY, "answerer")
    sources = retrieve.top_k(home, question, k)
    if not sources:
        raise Failure(f"{NO_SOURCES} for this question")

    answer = seams.run(command, home, citations.prompt(question, sources), "answerer")
    stray = citations.invented(answer, len(sources))
    if stray:
        cited = ", ".join(f"[{number}]" for number in stray)
        raise Failure(
            f"the answerer cited {cited}, which no retrieved source carries "
            f"({len(sources)} were provided) — refusing to print an invented citation"
        )
    print(citations.document(answer, sources))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ask", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    # One verb, two names: `run` is the boundary the evaluations drive, `answer` the
    # name the cli calls it by. Either rename would break a caller ask does not own.
    question = sub.add_parser("run", aliases=["answer"], help="answer from the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help=f"sources to retrieve (default {DEFAULT_K})")
    question.add_argument(
        "--fast", action="store_true", help="skip the librarian: retrieve, then answer"
    )
    args = parser.parse_args(argv)

    try:
        if args.k is not None and args.k < 1:
            raise Failure(f"-k must be at least 1 (got {args.k})", code=2)
        home, asked = home_dir(), " ".join(args.question)
        if args.fast:
            return fast(home, asked, DEFAULT_K if args.k is None else args.k)
        if args.k is not None:
            # -k sizes a retrieval the librarian does not do; say so rather than
            # letting the flag look as though it changed the answer.
            print("note: -k applies to --fast retrieval only", file=sys.stderr)
        return librarian(home, asked)
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
