"""Durable evals: FTS stemming (SPEC-index-003).

Boundary: `python -m index ...`. The porter tokenizer makes morphological
variants match in both directions, for reindex and incremental update alike.
"""

import json

from conftest import CHAPTERED_META, run_component, write_archive_page

STEM_SECTIONS = [
    (0, "Intro", "We are archiving videos about transcribing meetings."),
    (95, "Middle", "One video shows how a transcript gets searched."),
]


def idx(home, *args):
    return run_component("index", list(args), home)


def search_ids(home, query):
    r = idx(home, "search", query, "--json")
    assert r.returncode == 0, r.stderr
    return [row["video_id"] for row in json.loads(r.stdout)]


def test_singular_query_finds_plural_text_and_back(home):
    write_archive_page(home, CHAPTERED_META, STEM_SECTIONS)
    assert idx(home, "reindex").returncode == 0
    for query in ("video", "videos", "transcribe", "transcripts", "meeting", "archive"):
        assert search_ids(home, query), f"stemmed query {query!r} found nothing"


def test_incremental_update_stems_identically(home):
    write_archive_page(home, CHAPTERED_META, STEM_SECTIONS)
    assert idx(home, "update", CHAPTERED_META["id"]).returncode == 0
    # "meeting" appears only as "meetings" in the text — a literal match can't pass
    assert search_ids(home, "meeting"), "update-built index must stem like reindex"
