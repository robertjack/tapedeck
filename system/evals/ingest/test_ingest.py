"""Durable evals: ingest (SPEC-ingest-001, SPEC-core-004).

Boundary: `python -m ingest add <url> [--force]`, library via $TAPEDECK_HOME,
fetcher via config.toml [ingest].fetcher_command (see conftest.set_fetcher for
the pinned fetcher interface).
"""

import json

from conftest import run_component, set_fetcher

FETCH_OK = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/fetch-count"
printf 'fake video bytes' > "$TAPEDECK_DEST/video.mp4"
cat > "$TAPEDECK_DEST/info.json" <<'JSON'
{"id": "dQw4w9WgXcQ", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
 "description": "A fixture.",
 "chapters": [{"title": "Intro", "start_time": 0},
              {"title": "The Core Idea", "start_time": 95}]}
JSON
"""
FETCH_FAILS = """#!/bin/sh
printf 'partial junk' > "$TAPEDECK_DEST/video.mp4"
exit 1
"""
FETCH_NO_INFO = """#!/bin/sh
printf 'fake video bytes' > "$TAPEDECK_DEST/video.mp4"
"""

URL_FORMS = (
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "dQw4w9WgXcQ",
)


def add(home, *args):
    return run_component("ingest", ["add", *args], home)


def test_all_url_forms_resolve_to_the_canonical_id(home):
    set_fetcher(home, FETCH_OK)
    for url in URL_FORMS:
        r = add(home, url)
        assert r.returncode == 0, f"{url}: {r.stderr}"
    dirs = [p.name for p in (home / "library").iterdir() if p.is_dir()]
    assert dirs == ["dQw4w9WgXcQ"], f"unexpected library entries: {dirs}"


def test_garbage_url_is_a_usage_error(home):
    set_fetcher(home, FETCH_OK)
    r = add(home, "https://example.com/not-a-video")
    assert r.returncode == 2
    assert list((home / "library").iterdir()) == []


def test_meta_is_normalized_to_the_schema(home):
    set_fetcher(home, FETCH_OK)
    assert add(home, "dQw4w9WgXcQ").returncode == 0
    d = home / "library" / "dQw4w9WgXcQ"
    assert (d / "video.mp4").read_bytes() == b"fake video bytes"
    meta = json.loads((d / "meta.json").read_text())
    assert meta["id"] == "dQw4w9WgXcQ"
    assert meta["title"] == "Test Video: Building Things"
    assert meta["channel"] == "Fixture Channel"
    assert meta["upload_date"] == "2026-01-15"        # normalized from 20260115
    assert meta["duration_s"] == 720
    assert meta["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert meta["chapters"] == [
        {"title": "Intro", "start_s": 0},
        {"title": "The Core Idea", "start_s": 95},
    ]


def test_existing_video_skips_fetch_unless_forced(home):
    set_fetcher(home, FETCH_OK)
    assert add(home, "dQw4w9WgXcQ").returncode == 0
    assert add(home, "dQw4w9WgXcQ").returncode == 0
    assert (home / "fetch-count").read_text().count("run") == 1
    assert add(home, "dQw4w9WgXcQ", "--force").returncode == 0
    assert (home / "fetch-count").read_text().count("run") == 2


def test_failed_fetch_leaves_no_partial_entry(home):
    set_fetcher(home, FETCH_FAILS)
    r = add(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert not (home / "library" / "dQw4w9WgXcQ").exists()


def test_fetcher_without_info_json_fails_cleanly(home):
    set_fetcher(home, FETCH_NO_INFO)
    r = add(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert "info" in r.stderr.lower() or "meta" in r.stderr.lower()
    assert not (home / "library" / "dQw4w9WgXcQ").exists()


def test_missing_fetcher_config_is_an_error(home):
    (home / "config.toml").write_text("# no ingest section\n")
    r = add(home, "dQw4w9WgXcQ")
    assert r.returncode == 2
    assert "fetcher" in r.stderr.lower()
