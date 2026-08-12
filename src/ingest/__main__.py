"""Component boundary: `python -m ingest add <url> [--force]`.

Writes `library/<id>/video.<ext>` and `library/<id>/meta.json` — nothing else,
per the write-authority table in the layout contract. Exit codes follow
system/contracts/cli-surface.md: 0 success, 1 operation failure, 2 usage or
validation error. The entry path goes to stdout, diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import fetch, meta
from .sources import Unrecognized, canonical_id

DEFAULT_HOME = "~/dev/storage/tapedeck"
USAGE_ERRORS = (Unrecognized, fetch.ConfigError)
FAILURES = (fetch.FetchError, meta.BadMetadata, OSError)


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def is_complete(entry: Path) -> bool:
    """An entry only counts as ingested with both halves of what ingest owns."""
    return fetch.has_video(entry) and (entry / meta.META_NAME).is_file()


def add(home: Path, url: str, force: bool) -> int:
    video_id = canonical_id(url)
    entry = home / "library" / video_id
    if is_complete(entry) and not force:
        # Idempotent by default (SPEC-core-003): the video is the expensive part
        # and it is already here, so re-running `add` costs nothing.
        print(f"{video_id}: already ingested — skipping the fetch", file=sys.stderr)
        print(entry)
        return 0
    command = fetch.fetcher_command(home)
    staging = fetch.stage(home / "library", video_id)
    try:
        print(f"{video_id}: fetching…", file=sys.stderr)
        fetch.run(command, home, video_id, staging)
        video = fetch.find_video(staging)
        info = meta.read_info(meta.find_info(staging))
        meta.write(staging, meta.normalize(video_id, info))
        fetch.commit(staging, entry)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"{video_id}: fetched {video.name}", file=sys.stderr)
    print(entry)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    one = sub.add_parser("add", help="fetch one video into the library")
    one.add_argument("url", help="watch URL, youtu.be/shorts link, or bare video id")
    one.add_argument("--force", action="store_true", help="re-fetch a video already here")
    args = parser.parse_args(argv)

    try:
        return add(home_dir(), args.url, args.force)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
