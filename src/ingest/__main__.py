"""The ingest boundary: `python -m ingest add <url|path> [--force] [--verbose] | expand <url>`.

`add` puts exactly one video in the library, and is the sole writer of
`library/<id>/video.*` and `library/<id>/meta.json`. `expand` answers what a
playlist or channel URL contains, so a caller can sweep it one video at a time.

The order of `add_remote` is the whole safety story of SPEC-ingest-001. Everything
that can fail — the download, finding the video, reading the metadata, normalizing
it — happens in a staging directory beside the library, before the entry is
touched at all. Only when a complete, valid result is in hand does the entry
change, by a rename on the same filesystem. So a fetch that dies mid-write leaves
a fresh video unstarted rather than half-made, and leaves an existing one exactly
as it was: the old video byte-identical beside its old meta.json, still usable.

A target naming a file already on this machine (SPEC-ingest-005) is resolved
before anything is parsed as a URL at all — that decision belongs to `sources`,
ingest's own id grammar, and is never re-derived here. `add_local` never touches
the fetcher seam: nothing is downloaded, so a machine with no fetcher configured
can still add local footage. Its staging and atomic install are exactly
`add_remote`'s.

`add_remote` is quiet by default (SPEC-ingest-004): the fetcher's own chatter is
captured, not relayed, and what reaches stderr is ingest's own staging-bytes
heartbeat plus, on failure, the tool's captured words in full. `--verbose` turns
that off and streams the fetcher raw, as it always used to.

Exit codes are contracts/cli-surface.md's: 0 done, 1 the operation failed,
2 usage.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import fetch, local, meta, sources

DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY = "library"

USAGE_ERRORS = (sources.BadRequest, fetch.ConfigError)
FAILURES = (fetch.FetchError, meta.BadMeta, local.MediaError, OSError)


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def install(entry: Path, staged: Path, document: dict) -> None:
    """The only step that touches the entry, and the shortest one there is.

    The rename is atomic and the entry's old video survives until it lands; the
    leftovers go afterwards, so an entry never holds two videos and never holds a
    video that is still arriving. Works identically for a fetched file or a
    local-add symlink — `os.replace` moves the directory entry either way.
    """
    entry.mkdir(parents=True, exist_ok=True)
    landed = entry / staged.name
    os.replace(staged, landed)
    for old in fetch.videos(entry):
        if old != landed:
            old.unlink()
    meta.write(entry, document)


def add(home: Path, target: str, force: bool, verbose: bool = False) -> int:
    """One video into `library/<id>/`, or a reason it is not there."""
    source = sources.local_target(target)
    if source is not None:
        return add_local(home, source, force)
    return add_remote(home, target, force, verbose)


def add_local(home: Path, source: Path, force: bool) -> int:
    """A file already on this machine, installed by symlink with no fetcher
    involved (SPEC-ingest-005)."""
    video_id = sources.local_id(source)
    library = home / LIBRARY
    entry = library / video_id
    if not force and fetch.has_video(entry) and (entry / meta.META_NAME).is_file():
        print(entry)  # already here: no re-link, and the entry is still the answer
        return 0

    existed = entry.exists()
    dest = fetch.stage(library, video_id)
    try:
        document = meta.normalize(video_id, local.file_url(source), local.info(source))
        install(entry, local.install_link(dest, source), document)
    except BaseException:
        if not existed:
            shutil.rmtree(entry, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    print(entry)
    return 0


def add_remote(home: Path, target: str, force: bool, verbose: bool) -> int:
    """A YouTube URL or bare id, fetched through the configured seam."""
    video_id = sources.video_id(target)
    library = home / LIBRARY
    entry = library / video_id
    if not force and fetch.has_video(entry) and (entry / meta.META_NAME).is_file():
        print(entry)  # already here: no download, and the entry is still the answer
        return 0

    command = fetch.fetcher(home)
    url = sources.canonical_url(video_id)
    existed = entry.exists()
    dest = fetch.stage(library, video_id)
    try:
        fetch.run(command, home, video_id, url, dest, verbose=verbose)
        video = fetch.find_video(dest, video_id)
        document = meta.normalize(video_id, url, fetch.read_info(dest, video_id))
        install(entry, video, document)
    except BaseException:
        # A fetch that failed before the entry existed leaves nothing behind; one
        # that failed on an entry already here leaves it untouched, because
        # nothing above this line has touched it.
        if not existed:
            shutil.rmtree(entry, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    print(entry)
    return 0


def expand(home: Path, target: str) -> int:
    """The video ids a target names: its own, or its collection's (SPEC-ingest-002).

    A single video is answered from the URL grammar alone — asking an external
    tool what `youtu.be/<id>` contains would be a network round trip to learn what
    the id already says. Nothing reaches stdout until the listing is complete, so
    a failed lister prints no ids at all rather than a plausible-looking few.
    """
    kind, value = sources.resolve(target)
    if kind == sources.VIDEO:
        print(value)
        return 0
    listing = fetch.collect(fetch.lister(home), home, value)
    for video_id in sources.video_ids(listing):
        print(video_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest", description="Put videos in the tapedeck library."
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    fetching = verbs.add_parser("add", help="add one video into the library")
    fetching.add_argument(
        "url", help="a watch/shorts/youtu.be URL, a bare video id, or a local media path"
    )
    fetching.add_argument(
        "--force", action="store_true", help="re-fetch or re-link a video that is already here"
    )
    fetching.add_argument(
        "--verbose",
        action="store_true",
        help="stream the fetcher's raw output instead of a byte-progress heartbeat",
    )
    listing = verbs.add_parser("expand", help="print the video ids a URL names")
    listing.add_argument("url", help="a video URL, or a playlist or channel URL")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    home = home_dir()
    try:
        if args.verb == "add":
            return add(home, args.url, args.force, args.verbose)
        return expand(home, args.url)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
