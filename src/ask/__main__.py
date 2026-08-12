"""Component boundary: `python -m ask run <question> [-k N]` (alias: `answer`).

Reads the index's database and config.toml and writes nothing anywhere — ask owns
no path in system/contracts/library-layout.md. Exit codes follow
system/contracts/cli-surface.md: 0 success, 1 operation failure, 2 usage or
configuration error. The answer goes to stdout, everything else to stderr.

The order below is the whole design (SPEC-ask-001): configure, retrieve, and only
then think. A question the library cannot speak to stops at retrieval — no
answerer is run, because a model with no sources would answer from itself.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import answerer, citations, retrieve

DEFAULT_HOME = "~/dev/storage/tapedeck"
DEFAULT_K = 8
NOTHING_RETRIEVED = "no sources in the library for this question"

USAGE_ERRORS = (answerer.ConfigError,)
FAILURES = (answerer.AnswerError, retrieve.IndexUnreadable, OSError)


class Failure(RuntimeError):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def answer(home: Path, question: str, k: int) -> int:
    if k < 1:
        raise Failure(f"-k must be at least 1 (got {k})", code=2)
    command = answerer.seam(home)
    sources = retrieve.top_k(home, question, k)
    if not sources:
        raise Failure(NOTHING_RETRIEVED)
    text = answerer.run(command, home, citations.prompt(question, sources))
    stray = citations.invented(text, len(sources))
    if stray:
        cited = ", ".join(f"[{number}]" for number in stray)
        raise Failure(
            f"the answerer cited {cited}, which no retrieved source carries "
            f"({len(sources)} were provided) — refusing to print an invented citation"
        )
    print(citations.document(text, sources))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ask", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    # One verb, two names: `run` is the boundary the evaluations drive, `answer`
    # the name the cli calls it by. Renaming either would break a caller ask does
    # not own, and both mean the same thing to a reader.
    question = sub.add_parser("run", aliases=["answer"], help="answer from the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, default=DEFAULT_K, help=f"sources (default {DEFAULT_K})")
    args = parser.parse_args(argv)

    try:
        return answer(home_dir(), " ".join(args.question), args.k)
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except FAILURES as exc:
        return _report(exc, 1)
    except Failure as exc:
        return _report(exc, exc.code)


def _report(exc: Exception, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
