"""The verbs that mutate the library: `add`, `retranscribe`, `rm`
(SPEC-cli-002, SPEC-cli-003, SPEC-cli-004, SPEC-cli-009's auto-filing).
"""

from __future__ import annotations

import json
import shutil
import sys
import tomllib
from pathlib import Path

from ingest import sources as ingest_sources
from transcribe import transcriber as transcribe_transcriber

from . import components

CONFIG_NAME = "config.toml"

# --- add (SPEC-cli-003) --------------------------------------------------


def cmd_add(args, home: Path) -> int:
    url = args.url
    force = args.force
    try:
        kind, value = ingest_sources.resolve(url)
    except ingest_sources.BadRequest as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if kind == ingest_sources.COLLECTION and force:
        print(
            "error: --force is not allowed on a collection — add one video "
            "at a time to re-fetch it deliberately",
            file=sys.stderr,
        )
        return 2

    if kind == ingest_sources.VIDEO:
        ids = [value]
    else:
        rc, listing = components.run_capture_stdout("ingest", ["expand", url], home)
        if rc != 0:
            return rc
        ids = [line.strip() for line in listing.splitlines() if line.strip()]

    added = skipped = failed = 0
    for vid in ids:
        if not force and _is_complete(home, vid):
            skipped += 1
            continue
        if _run_video_pipeline(home, vid, force):
            added += 1
            _autofile(home, vid)
        else:
            failed += 1
    print(f"{added} added, {skipped} already present, {failed} failed")
    return 1 if failed else 0


def _is_complete(home: Path, vid: str) -> bool:
    entry = home / "library" / vid
    return (
        components.has_media(entry)
        and (entry / "transcript.json").is_file()
        and (home / "archive" / f"{vid}.md").is_file()
    )


def _run_video_pipeline(home: Path, vid: str, force: bool) -> bool:
    steps = [
        ("ingest", ["add", vid, *(["--force"] if force else [])]),
        ("transcribe", ["run", vid]),
        ("archive", ["render", vid]),
        ("index", ["update", vid]),
    ]
    for module, cmd_args in steps:
        rc = components.run_quiet(module, cmd_args, home)
        if rc != 0:
            print(f"error: {vid}: {module} failed (exit {rc})", file=sys.stderr)
            return False
    return True


def _read_wiki_config(home: Path) -> dict:
    path = home / CONFIG_NAME
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        doc = {}
    section = doc.get("wiki")
    return section if isinstance(section, dict) else {}


def _wiki_auto(home: Path) -> bool:
    value = _read_wiki_config(home).get("auto")
    return True if value is None else bool(value)


def _wiki_maintainer_command(home: Path) -> str | None:
    value = _read_wiki_config(home).get("maintainer_command")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _autofile(home: Path, vid: str) -> None:
    """The best-effort epilogue: a filing that cannot happen costs one
    stderr note, never `add`'s exit code, counts, or stdout (SPEC-cli-009)."""
    if not _wiki_auto(home):
        return
    if _wiki_maintainer_command(home) is None:
        print(
            f"note: {vid}: wiki filing skipped — no [wiki].maintainer_command "
            "configured",
            file=sys.stderr,
        )
        return
    rc = components.run_quiet("wiki", ["file", vid], home)
    if rc != 0:
        print(f"note: {vid}: the wiki filing failed (exit {rc})", file=sys.stderr)


# --- retranscribe (SPEC-cli-004) -----------------------------------------


def cmd_retranscribe(args, home: Path) -> int:
    try:
        _, target_model = transcribe_transcriber.seam(home)
    except transcribe_transcriber.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    selected = _select_for_retranscribe(home, target_model)

    if args.dry_run:
        for vid in selected:
            print(vid)
        return 0

    failed = 0
    for vid in selected:
        ok = (
            components.run_quiet("transcribe", ["run", vid, "--force"], home) == 0
            and components.run_quiet("archive", ["render", vid], home) == 0
            and components.run_quiet("index", ["update", vid], home) == 0
        )
        if not ok:
            failed += 1
            print(f"error: {vid}: retranscribe failed", file=sys.stderr)
    if selected or failed:
        print(f"{len(selected) - failed} redone, {failed} failed")
    return 1 if failed else 0


def _select_for_retranscribe(home: Path, target_model: str) -> list[str]:
    library = home / "library"
    if not library.is_dir():
        return []
    selected = []
    for entry in sorted(p for p in library.iterdir() if p.is_dir()):
        name = entry.name
        if components.is_video_id(name):
            if not components.has_media(entry):
                print(
                    f"note: {name}: no video file — cannot retranscribe without "
                    "re-downloading it, skipped",
                    file=sys.stderr,
                )
                continue
            if _transcript_model(entry) != target_model:
                selected.append(name)
            continue
        staged_for = components.staging_video(name)
        if staged_for is not None:
            print(
                f"note: library/{name} is a tapedeck download in progress for "
                f"{staged_for} — left alone, skipped",
                file=sys.stderr,
            )
            continue
        print(f"note: library/{name} is not a tapedeck video — skipped", file=sys.stderr)
    return selected


def _transcript_model(entry: Path) -> str | None:
    path = entry / "transcript.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    label = doc.get("model") if isinstance(doc, dict) else None
    return label if isinstance(label, str) else None


# --- rm (SPEC-cli-002, SPEC-cli-009) --------------------------------------


def cmd_rm(args, home: Path) -> int:
    vid = args.video_id
    entry = home / "library" / vid
    if not components.is_video_id(vid) or not entry.is_dir():
        print(f"error: {vid!r} is not a known video id", file=sys.stderr)
        return 2

    if args.media_only:
        for video in components.video_files(entry):
            video.unlink()
        print(vid)
        return 0

    shutil.rmtree(entry, ignore_errors=True)
    page = home / "archive" / f"{vid}.md"
    if page.is_file():
        page.unlink()
    components.run_quiet("index", ["update", vid], home)

    wiki_page = home / "wiki" / "sources" / f"{vid}.md"
    if wiki_page.is_file():
        print(
            f"note: {vid}: the wiki still holds a page for this video — "
            "`tapedeck wiki lint` will name it",
            file=sys.stderr,
        )
    print(vid)
    return 0
