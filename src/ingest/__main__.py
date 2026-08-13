"""Component boundary: `python -m ingest add <url|id> [--force]`.

Writes `library/<id>/video.<ext>` and `library/<id>/meta.json` — nothing else,
per the write-authority table in the layout contract. A transcript already
sitting beside them belongs to transcribe and survives a `--force` re-fetch
untouched; the cli re-derives it. Exit codes follow contracts/cli-surface.md: 0
success, 1 operation failure, 2 usage or validation error. The entry directory
goes to stdout, progress and diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import fetch, meta, sources

DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY = "library"

USAGE_ERRORS = (sources.BadRequest, fetch.ConfigError)
FAILURES = (fetch.FetchError, meta.BadMeta, OSError)


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def install(entry: Path, video: Path, document: dict) -> None:
    """Move a finished fetch into `library/<id>/`: the video first, then the
    metadata that makes the entry complete. Interrupted between the two, the
    entry reads as unfinished and the next `add` re-fetches it (SPEC-core-003).
    An entry we created and could not finish is removed on the way out — a
    failed fetch leaves nothing behind."""
    created = not entry.exists()
    try:
        entry.mkdir(parents=True, exist_ok=True)
        # A re-fetch can land on a different container (mp4 where mkv was), and
        # two `video.*` files would leave every reader guessing which is real.
        for stale in fetch.videos(entry):
            stale.unlink()
        shutil.move(str(video), entry / video.name)
        meta.write(entry, document)
    except OSError:
        if created:
            shutil.rmtree(entry, ignore_errors=True)
        raise


def add(home: Path, target: str, force: bool) -> int:
    video_id = sources.video_id(target)
    entry = home / LIBRARY / video_id
    if fetch.has_video(entry) and (entry / meta.META_NAME).is_file() and not force:
        # Idempotent by default (SPEC-core-003): the download is the expensive
        # part and this video is already here. `--force` fetches it again.
        print(f"{video_id}: already in the library — skipping the fetch", file=sys.stderr)
        print(entry)
        return 0
    command = fetch.seam(home)
    url = sources.canonical_url(video_id)
    staging = fetch.stage()
    try:
        print(f"{video_id}: fetching {url}…", file=sys.stderr)
        fetch.run(command, home, video_id, url, staging)
        video = fetch.find_video(staging, video_id)
        document = meta.normalize(video_id, url, fetch.read_info(staging, video_id))
        install(entry, video, document)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"{video_id}: {document['title']} ({document['duration_s']}s)", file=sys.stderr)
    print(entry)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    one = sub.add_parser("add", help="fetch one video into the library")
    one.add_argument("target", help="a watch, youtu.be or shorts URL, or a bare video id")
    one.add_argument("--force", action="store_true", help="re-fetch a video already here")
    args = parser.parse_args(argv)

    try:
        return add(home_dir(), args.target, args.force)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
