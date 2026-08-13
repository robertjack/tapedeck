"""The tapedeck executable (SPEC-cli-001, contracts/cli-surface.md).

Seven verbs, no more: adding one is a change to the durable layer, not to this
file. Everything here is one of three things — resolving $TAPEDECK_HOME, driving
the components that own the work, or reading the library for the two verbs no
component owns. Human output goes to stdout, progress and diagnostics to stderr,
and the exit code is 0, 1 (the operation failed), or 2 (the request was wrong).

`add` is the only pipeline: ingest -> transcribe -> archive -> index, each step
the next one's precondition, each idempotent on its own, so re-running `add`
costs a re-render and nothing more (SPEC-core-003).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import library
from .components import ComponentError, delegate, step
from .home import resolve, scaffold


class Failure(Exception):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def _k(args) -> list[str]:
    """Forward -k only when asked, so each component keeps its own default."""
    return ["-k", str(args.k)] if args.k is not None else []


def add(home: Path, args) -> int:
    force = ["--force"] if args.force else []
    fetched = step("ingest", ["add", *force, "--", args.url], home)
    video_id = Path(fetched.splitlines()[-1]).name if fetched else ""
    if not library.VIDEO_ID.fullmatch(video_id):
        raise Failure(f"ingest did not say which video it fetched (it said {fetched!r})")
    # --force means re-derive from the top: a freshly fetched video deserves a
    # transcript taken from it, not the one left over from the copy it replaced.
    step("transcribe", ["run", *force, "--", video_id], home)
    rendered = step("archive", ["render", "--", video_id], home)
    step("index", ["update", "--", video_id], home)
    meta = library.read_meta(home, video_id) or {}
    title = meta.get("title") or video_id
    print(f"{video_id}: ready — {title}", file=sys.stderr)
    print(rendered or library.page(home, video_id))
    return 0


def search(home: Path, args) -> int:
    flags = _k(args) + (["--json"] if args.json else [])
    return delegate("index", ["search", *flags, "--", " ".join(args.query)], home)


def ask(home: Path, args) -> int:
    return delegate("ask", ["run", *_k(args), "--", " ".join(args.question)], home)


def reindex(home: Path, args) -> int:
    return delegate("index", ["reindex"], home)


def show_list(home: Path, args) -> int:
    rows = library.videos(home)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("nothing in the library yet — `tapedeck add <url>` starts it", file=sys.stderr)
        return 0
    width = min(max(len(row["channel"]) for row in rows), 30)
    for row in rows:
        date = row["upload_date"] or "?" * 10
        print(f"{row['id']}  {date}  {row['channel']:<{width}}  {row['title']}")
    return 0


def show(home: Path, args) -> int:
    video_id = args.video_id
    meta = library.read_meta(home, video_id)
    if meta is None:
        raise Failure(f"{video_id!r} is not in the library", code=2)
    files = library.media(home, video_id)
    paths = {
        "library": str(library.entry(home, video_id)),
        "media": str(files[0]) if files else None,
        "transcript": _existing(library.entry(home, video_id) / "transcript.json"),
        "archive": _existing(library.page(home, video_id)),
    }
    if args.json:
        print(json.dumps({**meta, "paths": paths}, ensure_ascii=False, indent=2))
        return 0
    print(meta.get("title") or video_id)
    fields = [
        ("id", video_id),
        ("channel", meta.get("channel", "")),
        ("uploaded", meta.get("upload_date", "")),
        ("duration", library.clock(meta.get("duration_s"))),
        ("url", meta.get("url", "")),
        *((name, paths[name] or "(none)") for name in ("media", "transcript", "archive")),
    ]
    for label, value in fields:
        print(f"  {label:<11}{value}")
    return 0


def _existing(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def rm(home: Path, args) -> int:
    video_id = args.video_id
    if not library.VIDEO_ID.fullmatch(video_id) or not library.known(home, video_id):
        raise Failure(f"{video_id!r} is not in the library", code=2)
    if args.media_only:
        removed = library.delete_media(home, video_id)
        if not removed:
            print(f"{video_id}: no media file here — nothing to reclaim")
            return 0
        names = ", ".join(name for name, _ in removed)
        freed = library.size(sum(nbytes for _, nbytes in removed))
        # The knowledge stays; the source of truth does not (SPEC-core-002), so say so.
        print(f"{video_id}: re-transcribing it would mean downloading again", file=sys.stderr)
        print(f"{video_id}: removed {names} — {freed} reclaimed, knowledge kept")
        return 0
    # Page first, then the index that reads it, then the entry: interrupted at any
    # point the video is still recognisable, and `rm` again finishes the job.
    library.delete_page(home, video_id)
    step("index", ["update", "--", video_id], home)
    library.delete_entry(home, video_id)
    print(f"{video_id}: removed — library entry, archive page and index rows")
    return 0


VERBS = {
    "add": add,
    "search": search,
    "ask": ask,
    "list": show_list,
    "show": show,
    "reindex": reindex,
    "rm": rm,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tapedeck",
        description="A local video brain: download, transcribe, archive, ask.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    one = sub.add_parser("add", help="download, transcribe, archive and index one video")
    one.add_argument("url", help="watch URL, youtu.be/shorts link, or bare video id")
    one.add_argument("--force", action="store_true", help="re-fetch and re-derive from scratch")

    find = sub.add_parser("search", help="ranked timestamped excerpts with deep links")
    find.add_argument("query", nargs="+")
    find.add_argument("-k", type=int, help="how many results to show")
    find.add_argument("--json", action="store_true", help="emit the same fields structurally")

    question = sub.add_parser("ask", help="a cited answer grounded in the library")
    question.add_argument("question", nargs="+")
    question.add_argument("-k", type=int, help="how many sources to retrieve")

    listing = sub.add_parser("list", help="one line per video: id, date, channel, title")
    listing.add_argument("--json", action="store_true", help="emit the same fields structurally")

    single = sub.add_parser("show", help="metadata and paths for one video")
    single.add_argument("video_id")
    single.add_argument("--json", action="store_true", help="emit the same fields structurally")

    sub.add_parser("reindex", help="rebuild tapedeck.db from archive/ alone")

    drop = sub.add_parser("rm", help="remove a video everywhere, or just its media")
    drop.add_argument("video_id")
    drop.add_argument(
        "--media-only",
        action="store_true",
        help="delete only the video file, keeping transcript, archive page and index",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return VERBS[args.verb](scaffold(resolve()), args)
    except (Failure, ComponentError) as exc:
        return _report(exc, exc.code)
    except OSError as exc:
        return _report(exc, 1)
    except KeyboardInterrupt:
        # Every verb is re-runnable (SPEC-core-003), so stopping is always safe.
        return _report("interrupted", 1)


def _report(message, code: int) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
