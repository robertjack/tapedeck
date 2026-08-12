"""Component boundary: `python -m archive render <id> | render-all`.

Reads `library/<id>/{meta.json,transcript.json}` and writes `archive/<id>.md` —
nothing else, per the write-authority table in the layout contract. Exit codes
follow system/contracts/cli-surface.md: 0 success, 1 operation failure,
2 usage/validation error. Rendered page paths go to stdout, diagnostics to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from .render import page

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
DEFAULT_HOME = "~/dev/storage/tapedeck"


class Failure(Exception):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def _load(path, label, video_id):
    if not path.is_file():
        raise Failure(f"{video_id}: {label} is missing ({path})")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Failure(f"{video_id}: {label} is unreadable — {exc}") from exc
    if not isinstance(data, dict):
        raise Failure(f"{video_id}: {label} is not a JSON object")
    return data


def load_meta(video_dir: Path, video_id: str) -> dict:
    meta = _load(video_dir / "meta.json", "meta.json", video_id)
    for key in ("id", "title", "channel", "upload_date", "url"):
        if not isinstance(meta.get(key), str):
            raise Failure(f"{video_id}: meta.json needs a string {key!r}")
    if meta["id"] != video_id:
        raise Failure(f"{video_id}: meta.json claims id {meta['id']!r}")
    duration = meta.get("duration_s")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise Failure(f"{video_id}: meta.json needs a non-negative duration_s")
    meta["duration_s"] = int(duration)
    for chapter in meta.get("chapters") or []:
        ok = isinstance(chapter, dict) and isinstance(chapter.get("start_s"), (int, float))
        if not ok or isinstance(chapter.get("start_s"), bool):
            raise Failure(f"{video_id}: meta.json has a chapter without a numeric start_s")
    return meta


def load_transcript(video_dir: Path, video_id: str) -> dict:
    transcript = _load(video_dir / "transcript.json", "transcript.json", video_id)
    segments = transcript.get("segments")
    if not isinstance(segments, list) or not segments:
        raise Failure(f"{video_id}: transcript.json has no segments")
    for segment in segments:
        timed = isinstance(segment, dict) and all(
            isinstance(segment.get(k), (int, float)) and not isinstance(segment.get(k), bool)
            for k in ("start", "end")
        )
        if not timed or not isinstance(segment.get("text"), str):
            raise Failure(f"{video_id}: transcript.json has a malformed segment")
    return transcript


def write_page(home: Path, video_id: str, text: str) -> Path:
    """Atomic swap, so an interrupted render never leaves a half page behind."""
    out_dir = home / "archive"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{video_id}.md"
    # Dotted temp name: a crashed render stays invisible to an archive/*.md glob.
    tmp = out_dir / f".{video_id}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise Failure(f"{video_id}: could not write {target} — {exc}") from exc
    return target


def render_one(home: Path, video_id: str) -> Path:
    if not VIDEO_ID.fullmatch(video_id):
        raise Failure(f"{video_id!r} is not an 11-character video id", code=2)
    video_dir = home / "library" / video_id
    if not video_dir.is_dir():
        raise Failure(f"{video_id}: not in the library ({home / 'library'})", code=2)
    meta = load_meta(video_dir, video_id)
    transcript = load_transcript(video_dir, video_id)
    return write_page(home, video_id, page(meta, transcript))


def render_all(home: Path) -> int:
    library = home / "library"
    if not library.is_dir():
        print(f"no library at {library} — nothing to render", file=sys.stderr)
        return 0
    failed = 0
    for video_dir in sorted(p for p in library.iterdir() if p.is_dir()):
        video_id = video_dir.name
        if not (video_dir / "transcript.json").is_file():
            print(f"{video_id}: skipped, no transcript yet", file=sys.stderr)
            continue
        try:
            print(render_one(home, video_id))
        except Failure as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="archive", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    one = sub.add_parser("render", help="render archive/<id>.md for one video")
    one.add_argument("video_id")
    sub.add_parser("render-all", help="render every video that has a transcript")
    args = parser.parse_args(argv)

    try:
        if args.verb == "render":
            print(render_one(home_dir(), args.video_id))
            return 0
        return render_all(home_dir())
    except Failure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
