"""Component boundary: `python -m transcribe run <id> [--force] | from-parakeet`.

`run` writes `library/<id>/transcript.json` — nothing else, per the write-authority
table in the layout contract. The video beside it is the source of truth and is
only ever read. `from-parakeet` writes nothing at all: it is a filter, stdin to
stdout, so that a parakeet transcriber is a config edit (SPEC-transcribe-002).

Exit codes follow contracts/cli-surface.md: 0 success, 1 operation failure, 2
usage or validation error. The answer goes to stdout — the transcript path for
`run`, the adapted JSON for `from-parakeet` — progress and diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import document, parakeet, transcriber

DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY = "library"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class BadRequest(ValueError):
    """The target names no library entry."""


USAGE_ERRORS = (BadRequest, transcriber.ConfigError)
FAILURES = (
    transcriber.TranscribeError,
    document.BadTranscript,
    parakeet.NotParakeet,
    OSError,
)


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def transcribe(home: Path, video_id: str, force: bool) -> int:
    if not VIDEO_ID.fullmatch(video_id or ""):
        # The id is written into transcript.json and into every deep link built
        # from it, so it is checked before anything is derived under that name.
        raise BadRequest(f"{video_id!r} is not a video id — expected 11 characters")
    entry = home / LIBRARY / video_id
    source = transcriber.media(entry, video_id)
    target = entry / document.TRANSCRIPT_NAME
    if target.is_file() and not force:
        # Idempotent by default (SPEC-core-003): transcription is the expensive
        # step and this video already has one. `--force` re-derives it, which is
        # how a better model comes to supersede an older transcript.
        print(f"{video_id}: already transcribed — skipping", file=sys.stderr)
        print(target)
        return 0
    command, model = transcriber.seam(home)
    staging = transcriber.stage()
    try:
        out = transcriber.out_path(staging)
        print(f"{video_id}: transcribing {source.name} with {model}…", file=sys.stderr)
        transcriber.run(command, home, video_id, source, out)
        # Nothing has touched the entry yet: the output has to read as JSON and
        # normalize into real segments before a transcript exists at all, so a
        # transcriber that failed halfway leaves the library exactly as it was.
        payload = transcriber.read_output(out, source, video_id)
        transcript = document.normalize(video_id, model, payload)
        document.write(entry, transcript)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"{video_id}: {len(transcript['segments'])} segments ({model})", file=sys.stderr)
    print(target)
    return 0


def from_parakeet(stdin, stdout) -> int:
    """parakeet-mlx JSON in, whisper-shaped JSON out. Reads and writes nothing else."""
    adapted = parakeet.adapt(stdin.read())
    # Written in one go, after the parse: a failure here has printed nothing, which
    # is what the shell's `> "$TAPEDECK_OUT"` needs it to have printed.
    stdout.write(json.dumps(adapted, ensure_ascii=False) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transcribe", description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)

    one = verbs.add_parser("run", help="derive the transcript for one video in the library")
    one.add_argument("video_id", help="the 11-character id of a library entry")
    one.add_argument("--force", action="store_true", help="re-transcribe a video that has one")

    verbs.add_parser("from-parakeet", help="adapt parakeet-mlx JSON on stdin to the whisper shape")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verb == "run":
            return transcribe(home_dir(), args.video_id, args.force)
        return from_parakeet(sys.stdin, sys.stdout)
    except USAGE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
