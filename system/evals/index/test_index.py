"""Durable evals: the FTS index (SPEC-index-001, SPEC-index-002).

Boundary: `python -m index {reindex | update <id> | search <query> [-k N] [--json]}`,
library via $TAPEDECK_HOME. tapedeck.db is derived from archive/*.md alone; a chunk is
one archive-page section. Search JSON rows carry: video_id, title, start_s, timestamp,
excerpt, url.
"""

import json

from conftest import CHAPTERED_META, PLAIN_META, run_component, write_archive_page

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
    (610, "Wrap Up", "Thanks for watching, goodbye."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
    (600, "Part 3", "Block three content about scoring loaves."),
]


def idx(home, *args):
    return run_component("index", list(args), home)


def search_json(home, query, *extra):
    r = idx(home, "search", query, "--json", *extra)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def two_video_home(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = idx(home, "reindex")
    assert r.returncode == 0, r.stderr


def test_reindex_then_search_returns_timestamped_result(home):
    two_video_home(home)
    results = search_json(home, "regeneration")
    assert results, "no results for a term present in the archive"
    top = results[0]
    assert top["video_id"] == "dQw4w9WgXcQ"
    assert top["title"] == "Test Video: Building Things"
    assert top["start_s"] == 95
    assert top["timestamp"] == "0:01:35"
    assert top["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s"
    assert "regeneration" in top["excerpt"]


def test_human_output_carries_link_and_timestamp(home):
    two_video_home(home)
    r = idx(home, "search", "sourdough")
    assert r.returncode == 0, r.stderr
    assert "0:00:00" in r.stdout
    assert "watch?v=plainvide00&t=0s" in r.stdout


def test_k_limits_results(home):
    two_video_home(home)
    assert len(search_json(home, "content", "-k", "1")) == 1


def test_no_matches_is_quietly_empty(home):
    two_video_home(home)
    r = idx(home, "search", "xylophone")
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert search_json(home, "xylophone") == []


def test_deleting_the_database_loses_nothing(home):
    two_video_home(home)
    before = search_json(home, "regeneration")
    (home / "tapedeck.db").unlink()
    assert idx(home, "reindex").returncode == 0
    assert search_json(home, "regeneration") == before


def test_incremental_update_matches_full_reindex(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    assert idx(home, "reindex").returncode == 0
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    assert idx(home, "update", "plainvide00").returncode == 0
    incremental = search_json(home, "proofing")
    (home / "tapedeck.db").unlink()
    assert idx(home, "reindex").returncode == 0
    assert search_json(home, "proofing") == incremental


def test_update_replaces_stale_rows(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    assert idx(home, "reindex").returncode == 0
    write_archive_page(home, CHAPTERED_META, [(0, "Intro", "Completely new opening text.")])
    assert idx(home, "update", "dQw4w9WgXcQ").returncode == 0
    assert search_json(home, "fixture") == []
    assert search_json(home, "opening") != []
