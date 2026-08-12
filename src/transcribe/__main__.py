"""Component boundary: `python -m transcribe run <id> [--force]`.

Writes `library/<id>/transcript.json` — nothing else, per the write-authority
table in the layout contract. Exit codes follow system/contracts/cli-surface.md:
0 success, 1 operation failure, 2 usage or validation error. The transcript path
goes to stdout, progress and diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from . import transcriber
from .document import TRANSCRIPT_NAME, BadTranscript, normalize, write

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
DEFAULT_HOME = "~/dev/storage/tapedeck"


class BadRequest(ValueError):
    """The command line does not name a transcribable video."""


USAGE_ERRORS = (BadRequest, transcriber.ConfigError)
FAILURES = (transcriber.TranscribeError, BadTranscript, OSError)


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def transcribe(home: Path, video_id: str, force: bool) -> int:
    if not VIDEO_ID.fullmatch(video_id):
        raise BadRequest(f"{video_id!r} is not an 11-character video id")
    entry = home / "library" / video_id
    target = entry / TRANSCRIPT_NAME
    if target.is_file() and not force:
        # Idempotent by default (SPEC-core-003): transcription is the expensive part
        # and a transcript is already here. `--force` re-derives it (SPEC-core-002).
        print(f"{video_id}: already transcribed — skipping", file=sys.stderr)
        print(target)
        return 0
    command, model = transcriber.seam(home)
    media = transcriber.find_media(entry, video_id)
    staging = transcriber.stage()
    try:
        print(f"{video_id}: transcribing {media.name} with {model}…", file=sys.stderr)
        output = transcriber.run(command, home, video_id, media, staging)
        document = normalize(video_id, model, output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    write(entry, document)
    print(f"{video_id}: {len(document['segments'])} segments", file=sys.stderr)
    print(target)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="transcribe", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    one = sub.add_parser("run", help="transcribe one video already in the library")
    one.add_argument("video_id", help="the 11-character video id")
    one.add_argument("--force", action="store_true", help="re-derive an existing transcript")
    args = parser.parse_args(argv)

    try:
        return transcribe(home_dir(), args.video_id, args.force)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
