"""Component boundary: `python -m ask run <question> [-k N] [--fast] [--video <id>]`
and `python -m ask verify [--video <id>] [--require-citation]`.

Reads config.toml, the library's metadata and the index's database, and writes
nothing — ask owns no path in system/contracts/library-layout.md. Exit codes follow
system/contracts/cli-surface.md: 0 success, 1 operation failure, 2 usage or config
error; the answer goes to stdout, everything else to stderr.

Both answering modes are the same shape, and the order below is the whole design:
settle everything deterministic first, then think, then check what came back. Nothing
probabilistic runs until the library is known to have something to say — and, in
fast mode, until the index it would say it from is one this build can read — and no
answer reaches stdout before its citations have been checked against the library.

`verify` is the last of those steps standing on its own (SPEC-ask-005): the same
`citations.audit` librarian mode is judged by, applied to text a caller hands in on
stdin, with no seam run and nothing written. Callers outside ask — wiki deciding
whether to keep a page — get ask's verdict by asking ask, which is the only way the
two can be relied on to agree (LESSON-0003).
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
    asking, and neither a model nor a page should be spent on it (SPEC-ask-003)."""
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
    # An answer tapedeck cannot trace to a moment in the library is not one it prints,
    # so here — unlike in `verify` — a citation is always required.
    problems = citations.audit(answer, library, scope, require_citation=True)
    if problems:
        raise Failure("refusing this answer's citations:\n  " + "\n  ".join(problems))
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


def verify(library: Library, scope: str | None, require_citation: bool) -> int:
    """Text on stdin, verdict in the exit code, every violation named on stderr.

    Reads the library and reports: no seam runs and nothing is written, so a caller
    can run this inside its own accept-or-roll-back decision, on whatever text it
    holds, as often as it likes, without the run being a step to undo (SPEC-ask-005).
    """
    try:
        text = sys.stdin.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise Failure(f"could not read the text to verify — {exc}") from exc
    problems = citations.audit(text, library, scope, require_citation=require_citation)
    if problems:
        # All of them, not the first: a caller fixing a page wants the whole list.
        raise Failure("these citations do not hold:\n  " + "\n  ".join(problems))
    return 0


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ask", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    # One verb, two names: `run` is the boundary the evals drive, `answer` the name
    # the cli calls it by. Either rename breaks a caller ask does not own.
    question = sub.add_parser("run", aliases=["answer"], help="answer from the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help=f"sources to retrieve (default {DEFAULT_K})")
    question.add_argument("--fast", action="store_true", help="retrieve, then answer")
    question.add_argument("--video", help="answer from this library video alone")

    checker = sub.add_parser("verify", help="check text's citations against the library")
    checker.add_argument("--video", help="every citation must be to this video")
    checker.add_argument(
        "--require-citation", action="store_true", help="uncited text fails"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    try:
        home = home_dir()
        library = Library(home)
        if args.verb == "verify":
            # The scope is settled before a byte of stdin is read: an id that names
            # nothing is answered by one path lookup, not by reading the text.
            return verify(library, scope_for(library, args.video), args.require_citation)
        if args.k is not None and args.k < 1:
            raise Failure(f"-k must be at least 1 (got {args.k})", code=2)
        asked = " ".join(args.question)
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
