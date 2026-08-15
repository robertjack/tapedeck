"""Component boundary: `python -m index {reindex | update <id> | search <query>}`.

Reads `archive/*.md` and writes `tapedeck.db` — nothing else, per the
write-authority table in the layout contract. Exit codes follow
system/contracts/cli-surface.md: 0 success, 1 operation failure, 2 usage or
validation error. Results and artifact paths go to stdout, diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import store
from .pages import VIDEO_ID, Page, PageError, parse

DEFAULT_HOME = "~/dev/storage/tapedeck"
DEFAULT_K = 8
REINDEX_HINT = "run `tapedeck reindex` to rebuild it from archive/"


class Failure(Exception):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def read_page(path: Path) -> Page:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PageError(f"unreadable — {exc}") from exc
    return parse(text, stem=path.stem)


def reindex(home: Path) -> int:
    """Rebuild tapedeck.db from archive/*.md alone — the whole database, always.

    This is also the migration (SPEC-index-004): whatever is on disk, readable to
    this build or not, is replaced by a database written and stamped by it.
    """
    archive = home / "archive"
    pages, failed = [], 0
    if not archive.is_dir():
        print(f"no archive at {archive} — building an empty index", file=sys.stderr)
    for path in sorted(archive.glob("*.md")) if archive.is_dir() else []:
        try:
            pages.append(read_page(path))
        except PageError as exc:
            failed += 1
            print(f"error: {path.name}: {exc}", file=sys.stderr)
    try:
        target = store.build(home, pages)
    except (store.Unusable, sqlite3.Error, OSError) as exc:
        raise Failure(f"could not build the index — {exc}") from exc
    chunks = sum(len(page.sections) for page in pages)
    print(f"indexed {len(pages)} page(s), {chunks} section(s)", file=sys.stderr)
    print(target)
    return 1 if failed else 0


def update(home: Path, video_id: str) -> int:
    """Bring one video's rows in line with its archive page, or drop them."""
    if not VIDEO_ID.fullmatch(video_id):
        raise Failure(f"{video_id!r} is not an 11-character video id", code=2)
    path = home / "archive" / f"{video_id}.md"
    page = None
    if path.is_file():
        try:
            page = read_page(path)
        except PageError as exc:
            raise Failure(f"{video_id}: {exc}") from exc
    else:
        print(f"{video_id}: no archive page — dropping its rows", file=sys.stderr)
    try:
        target = store.replace_video(home, video_id, page)
    except store.Unusable as exc:
        if exc.missing:
            # There is no index yet, so there is nothing to update and nothing to
            # be wrong about: a full build covers this video along with the rest.
            return reindex(home)
        # A database laid out by another schema is one this build would be
        # guessing at, and writing into a guess is worse than reading one
        # (SPEC-index-004). Rebuilding is the caller's move, not ours to take.
        raise Failure(f"{video_id}: {exc} — {REINDEX_HINT}") from exc
    except (sqlite3.Error, OSError) as exc:
        raise Failure(f"{video_id}: could not update the index — {exc}") from exc
    print(target)
    return 0


def _block(result: dict) -> str:
    """One human-readable hit: where it is, what was said, how to watch it."""
    headline = f"{result['timestamp']}  {result['title']}"
    if result["section"]:
        headline += f" — {result['section']}"
    lines = [headline]
    if result["excerpt"]:
        lines.append(f"    {result['excerpt']}")
    lines.append(f"    {result['url']}")
    return "\n".join(lines)


def search(home: Path, query: str, limit: int, as_json: bool) -> int:
    """Ranked matches, or silence — no results is an answer (SPEC-index-002)."""
    if limit < 1:
        raise Failure(f"-k must be at least 1 (got {limit})", code=2)
    try:
        results = store.search(home, query, limit)
    except store.Unusable as exc:
        raise Failure(f"{exc} — {REINDEX_HINT}") from exc
    except sqlite3.OperationalError as exc:
        # The query is made safe before it reaches fts5, so this is a long shot —
        # but a query fts5 refuses is the caller's problem, not the index's.
        if "fts5" in str(exc):
            raise Failure(f"{query!r} is not a query fts5 can run — {exc}", code=2) from exc
        raise Failure(f"the index could not be read — {exc}; {REINDEX_HINT}") from exc
    except sqlite3.Error as exc:
        raise Failure(f"the index could not be read — {exc}; {REINDEX_HINT}") from exc
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif results:
        print("\n\n".join(_block(result) for result in results))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="index", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("reindex", help="rebuild tapedeck.db from archive/*.md")
    one = sub.add_parser("update", help="refresh one video's rows after a re-render")
    one.add_argument("video_id")
    find = sub.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+")
    find.add_argument("-k", type=int, default=DEFAULT_K, help=f"max results (default {DEFAULT_K})")
    find.add_argument("--json", action="store_true", help="emit the same fields structurally")
    args = parser.parse_args(argv)

    try:
        home = home_dir()
        if args.verb == "reindex":
            return reindex(home)
        if args.verb == "update":
            return update(home, args.video_id)
        return search(home, " ".join(args.query), args.k, args.json)
    except Failure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
