"""The verbs that walk the library: `add`, `retranscribe`, `rm`, `list`, `show`.

`add` and `retranscribe` orchestrate the derivation chain — ingest -> transcribe
-> archive -> index — by calling each sibling's own module boundary in turn
(SPEC-cli-003, SPEC-cli-004); `rm`, `list` and `show` read `library/` directly,
asking ingest what counts as a video rather than deciding it here (LESSON-0003).
"""

from __future__ import annotations

import json
import shutil
import sys
import tomllib
from pathlib import Path

import archive
import ingest
from wiki import layout as wiki_layout

from .components import run_module, wiki_epilogue

FETCH_HELP_HINT = (
    'see "tapedeck help manual" for common causes, or run '
    '"tapedeck setup --refresh" to update the fetcher'
)


# --- add -----------------------------------------------------------------


def is_complete(home: Path, video_id: str) -> bool:
    """Media present by ingest's rule, a transcript, and an archive page — the
    whole of what a sweep skips re-deriving (SPEC-cli-003)."""
    entry = home / "library" / video_id
    return (
        ingest.has_video(entry)
        and (entry / "transcript.json").is_file()
        and (home / "archive" / f"{video_id}.md").is_file()
    )


def close_out(home: Path, video_id: str) -> None:
    """One stderr line in the user's terms — title, channel, duration
    (SPEC-cli-012) — read from the entry's own meta.json, nothing re-derived."""
    try:
        meta = json.loads((home / "library" / video_id / "meta.json").read_text())
    except (OSError, ValueError):
        return
    duration = archive.hms(meta.get("duration_s", 0))
    channel = meta.get("channel") or ""
    title = meta.get("title", video_id)
    tail = f" — {channel}" if channel else ""
    print(f"tapedeck: added {title}{tail} ({duration})", file=sys.stderr)


def pipeline_one(home: Path, video_id: str, target: str, force: bool, verbose: bool) -> bool:
    args = ["add", target]
    if force:
        args.append("--force")
    if verbose:
        args.append("--verbose")
    if run_module(home, "ingest", args).returncode != 0:
        print(f"error: {video_id}: fetch failed — {FETCH_HELP_HINT}", file=sys.stderr)
        return False
    if run_module(home, "transcribe", ["run", video_id]).returncode != 0:
        print(f"error: {video_id}: transcription failed", file=sys.stderr)
        return False
    if run_module(home, "archive", ["render", video_id]).returncode != 0:
        print(f"error: {video_id}: archive render failed", file=sys.stderr)
        return False
    if run_module(home, "index", ["update", video_id]).returncode != 0:
        print(f"error: {video_id}: index update failed", file=sys.stderr)
        return False
    return True


def add(home: Path, target: str, force: bool, verbose: bool) -> int:
    try:
        kind, value = ingest.resolve(target)
    except ingest.BadRequest as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if kind == ingest.COLLECTION:
        if force:
            print(
                "error: --force is single-video only — add one video at a "
                "time to re-fetch it deliberately",
                file=sys.stderr,
            )
            return 2
        listing = run_module(home, "ingest", ["expand", target])
        if listing.returncode != 0:
            print(f"error: could not expand {target}", file=sys.stderr)
            return 1
        ids = [line.strip() for line in (listing.stdout or "").splitlines() if line.strip()]
        targets = {video_id: ingest.canonical_url(video_id) for video_id in ids}
    else:
        ids, targets = [value], {value: target}

    added_n = already = failed = 0
    filed_ids: list[str] = []
    for video_id in ids:
        if not force and is_complete(home, video_id):
            already += 1
            continue
        if pipeline_one(home, video_id, targets[video_id], force, verbose):
            added_n += 1
            close_out(home, video_id)
            filed_ids.append(video_id)
        else:
            failed += 1

    print(f"{added_n} added, {already} already present, {failed} failed")
    wiki_epilogue(home, filed_ids)
    return 1 if failed else 0


# --- retranscribe ----------------------------------------------------------


def _configured_model(home: Path) -> str | None:
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = (config.get("transcribe") or {}).get("model")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _current_label(entry: Path) -> str | None:
    try:
        doc = json.loads((entry / "transcript.json").read_text())
    except (OSError, ValueError):
        return None
    label = doc.get("model")
    return label if isinstance(label, str) else None


def _select_for_retranscribe(home: Path, model: str) -> list[str]:
    """Only what the sweep could actually re-derive (SPEC-cli-004): a
    well-formed video id, whose media ingest still has. Everything else under
    `library/` is reported and left alone — a staging directory in flight is
    tapedeck's own (SPEC-ingest-003), never called a stranger's."""
    selected = []
    for entry in sorted((home / "library").iterdir()):
        name = entry.name
        staged = ingest.staging(name)
        if staged is not None:
            print(f"{name}: tapedeck is still fetching {staged} here — skipped", file=sys.stderr)
            continue
        if not ingest.VIDEO_ID.fullmatch(name):
            print(f"{name}: not a video — skipped", file=sys.stderr)
            continue
        if not ingest.has_video(entry):
            print(f"{name}: no video file — media was reclaimed, skipped", file=sys.stderr)
            continue
        if _current_label(entry) != model:
            selected.append(name)
    return selected


def retranscribe(home: Path, dry_run: bool) -> int:
    model = _configured_model(home)
    if model is None or not (home / "library").is_dir():
        return 0
    selected = _select_for_retranscribe(home, model)

    if dry_run:
        for video_id in selected:
            print(video_id)
        return 0

    failed = 0
    for video_id in selected:
        if run_module(home, "transcribe", ["run", video_id, "--force"]).returncode != 0:
            print(f"error: {video_id}: transcription failed", file=sys.stderr)
            failed += 1
            continue
        if run_module(home, "archive", ["render", video_id]).returncode != 0:
            print(f"error: {video_id}: archive render failed", file=sys.stderr)
            failed += 1
            continue
        if run_module(home, "index", ["update", video_id]).returncode != 0:
            print(f"error: {video_id}: index update failed", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


# --- rm / list / show --------------------------------------------------------


def rm(home: Path, video_id: str, media_only: bool) -> int:
    if not ingest.VIDEO_ID.fullmatch(video_id):
        print(f"error: {video_id!r} is not a video id", file=sys.stderr)
        return 2
    entry = home / "library" / video_id
    if not entry.is_dir():
        print(f"error: {video_id}: not in the library", file=sys.stderr)
        return 2
    if media_only:
        for path in ingest.videos(entry):
            path.unlink()
        return 0

    shutil.rmtree(entry, ignore_errors=True)
    (home / "archive" / f"{video_id}.md").unlink(missing_ok=True)
    run_module(home, "index", ["update", video_id])
    wiki_dir = wiki_layout.wiki_dir(home)
    if wiki_layout.filed(wiki_dir, video_id):
        print(
            f"note: the wiki still holds a page for {video_id} — "
            "`tapedeck wiki lint` will name it",
            file=sys.stderr,
        )
    return 0


def _load_meta(entry: Path) -> dict | None:
    try:
        return json.loads((entry / "meta.json").read_text())
    except (OSError, ValueError):
        return None


def list_videos(home: Path, as_json: bool) -> int:
    library = home / "library"
    rows = []
    if library.is_dir():
        for entry in sorted(library.iterdir()):
            if not ingest.VIDEO_ID.fullmatch(entry.name):
                continue
            meta = _load_meta(entry)
            if meta is not None:
                rows.append(meta)
    rows.sort(key=lambda m: (m.get("upload_date") or "", m.get("id") or ""))
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for meta in rows:
            print(
                f"{meta.get('id')}  {meta.get('upload_date', '?')}  "
                f"{meta.get('channel', '?')}  {meta.get('title', '?')}"
            )
    return 0


def show(home: Path, video_id: str, as_json: bool) -> int:
    if not ingest.VIDEO_ID.fullmatch(video_id):
        print(f"error: {video_id!r} is not a video id", file=sys.stderr)
        return 2
    entry = home / "library" / video_id
    meta = _load_meta(entry) if entry.is_dir() else None
    if meta is None:
        print(f"error: {video_id}: not in the library", file=sys.stderr)
        return 2
    media = ingest.videos(entry)
    archive_page = home / "archive" / f"{video_id}.md"
    result = {
        **meta,
        "media": str(media[0]) if media else None,
        "archive": str(archive_page) if archive_page.is_file() else None,
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"id: {meta.get('id')}")
    print(f"title: {meta.get('title')}")
    print(f"channel: {meta.get('channel')}")
    print(f"upload_date: {meta.get('upload_date')}")
    print(f"duration: {archive.hms(meta.get('duration_s', 0))}")
    print(f"media: {result['media'] or '(missing)'}")
    print(f"archive: {result['archive'] or '(not rendered)'}")
    return 0
