"""The tapedeck entrypoint (SPEC-cli-001, contracts/cli-surface.md).

Six verbs, exactly: add, search, ask, list, show, reindex. Adding a seventh is a
durable-layer change, not a patch here — the surface is a promise, and every
verb on it is idempotent (SPEC-core-003), so re-running anything is safe.

Every run resolves $TAPEDECK_HOME and makes it usable, then does one thing:
`add` walks the derivation chain component by component, `search`, `ask` and
`reindex` are handed to the component that owns them, `list` and `show` are
answered here from the library on disk. Human output to stdout, progress and
diagnostics to stderr; exit 0 success, 1 operation failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Failure, components, library
from .home import prepare, resolve

CHAIN_HINT = "no videos yet — `tapedeck add <url>`"


def step(module: str, args: list[str], home) -> components.Result:
    """One link of the chain. A step that fails stops the rest with its own exit
    code: a page rendered from a transcript that was never written, or an index
    row for a page that failed to render, would be worse than stopping here."""
    print(f"→ {module}", file=sys.stderr)
    result = components.run(module, args, home, capture=True)
    if result.code:
        raise Failure(f"{module} exited {result.code}", result.code)
    return result


def add(home, args) -> int:
    """video → transcript → archive page → index rows (SPEC-core-002), each link
    run by the component that owns it and each idempotent on its own, so a
    re-run costs only what is actually missing. `--force` re-fetches, and
    re-transcribes with it: after a new download the old transcript describes a
    file that is no longer there."""
    force = ["--force"] if args.force else []
    ingested = step("ingest", ["add", args.url, *force], home)
    video_id = library.ingested_id(ingested.stdout)
    step("transcribe", ["run", video_id, *force], home)
    step("archive", ["render", video_id], home)
    step("index", ["update", video_id], home)
    print(library.archive_page(home, video_id))
    return 0


def search(home, args) -> int:
    flags = ["--json"] if args.json else []
    if args.k is not None:
        flags += ["-k", str(args.k)]
    # `--` first: a query is the user's words, and words may start with a dash.
    return components.run("index", ["search", *flags, "--", *args.query], home).code


def ask(home, args) -> int:
    flags = ["-k", str(args.k)] if args.k is not None else []
    return components.run("ask", ["run", *flags, "--", *args.question], home).code


def reindex(home, args) -> int:
    return components.run("index", ["reindex"], home).code


def show_list(home, args) -> int:
    found = library.records(home)
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    elif found:
        print(library.listing(found))
    else:
        print(CHAIN_HINT, file=sys.stderr)
    return 0


def show_one(home, args) -> int:
    found = library.one(home, args.video_id)
    print(json.dumps(found, ensure_ascii=False, indent=2) if args.json else library.detail(found))
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="tapedeck", description="A local video brain.")
    sub = top.add_subparsers(dest="verb", required=True)

    one = sub.add_parser("add", help="ingest, transcribe, archive and index one video")
    one.add_argument("url", help="watch URL, youtu.be/shorts link, or bare video id")
    one.add_argument("--force", action="store_true", help="re-fetch and re-derive it")
    one.set_defaults(run=add)

    find = sub.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+")
    find.add_argument("-k", type=int, help="max results")
    find.add_argument("--json", action="store_true")
    find.set_defaults(run=search)

    question = sub.add_parser("ask", help="an answer from the library, with citations")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help="sources to retrieve")
    question.set_defaults(run=ask)

    every = sub.add_parser("list", help="one line per video in the library")
    every.add_argument("--json", action="store_true")
    every.set_defaults(run=show_list)

    detail = sub.add_parser("show", help="metadata and archive path for one video")
    detail.add_argument("video_id", help="the 11-character video id")
    detail.add_argument("--json", action="store_true")
    detail.set_defaults(run=show_one)

    rebuild = sub.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")
    rebuild.set_defaults(run=reindex)
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)  # an unknown verb or a missing argument exits 2
    try:
        return args.run(prepare(resolve()), args)
    except Failure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        # Nothing here is half-done in a way a re-run cannot finish (SPEC-core-003).
        print("interrupted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
