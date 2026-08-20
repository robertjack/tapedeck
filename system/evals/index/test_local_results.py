"""Durable evals: a local result addresses the moment it was read from
(SPEC-index-002 as amended, SPEC-index-001,
SPEC-index-002, SPEC-ingest-005).

Boundary: `python -m index`, over an archive page whose section headings carry
`file://` addresses instead of YouTube ones. This component owes the local-file
round no change — it reads the seconds out of whatever address a heading
carries and never cared about the host — and that is precisely the claim worth
pinning rather than assuming, since "no change owed" is a decision, not an
absence of one.
"""

import json

from conftest import run_component, write_archive_page

LOCAL_ID = "loc4lvide01"
LOCAL_URL = "file:///Users/somebody/Footage/standup.mp4"

LOCAL_META = {
    "id": LOCAL_ID,
    "title": "standup",
    "channel": "",
    "upload_date": "2026-03-04",
    "duration_s": 720,
    "url": LOCAL_URL,
}
SECTIONS = [
    (0, "Intro", "Morning everyone, quick standup."),
    (310, "The Migration", "The sourdough migration finished overnight."),
]


def indexed(home):
    write_archive_page(home, LOCAL_META, SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr


def search_json(home, query):
    r = run_component("index", ["search", query, "--json"], home)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_local_page_is_searchable_with_its_own_address(home):
    indexed(home)
    results = search_json(home, "migration")
    assert results, "a local video's words must be findable like any other"
    row = results[0]
    assert row["video_id"] == LOCAL_ID
    assert row["start_s"] == 310, (
        f"the section's seconds come out of the address it carries: {row!r}"
    )
    assert row["url"].startswith("file://"), (
        f"a result addresses the moment the way the page did — pointing a local "
        f"result at youtube.com would send the reader to somebody else's video: "
        f"{row['url']!r}"
    )
    assert "?t=310s" in row["url"] or "&t=310s" in row["url"], row["url"]
