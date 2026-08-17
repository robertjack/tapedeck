"""Durable evals: a paragraph's leading anchor is metadata, not prose
(SPEC-index-005).

Boundary: `python -m index`, over archive pages written directly in the shape
SPEC-archive-002 pins — frontmatter, `## [h:mm:ss](deep-link) Title` sections,
and paragraphs that open with their own `[h:mm:ss](deep-link) `. Pages are
written by hand rather than rendered, exactly as test_index.py writes its own:
this suite must stay red or green on the index's behavior alone, whichever
state the archive component is in.
"""

import json

from conftest import CHAPTERED_META, PLAIN_META, run_component, write_archive_page


def deep(video_id, hms, seconds):
    return f"[{hms}](https://www.youtube.com/watch?v={video_id}&t={seconds}s)"


# The bodies SPEC-archive-002 produces: one leading anchor, then prose.
CH_SECTIONS = [
    (0, "Intro", f"{deep('dQw4w9WgXcQ', '0:00:00', 0)} Welcome to the fixture show."),
    (95, "The Core Idea",
     f"{deep('dQw4w9WgXcQ', '0:01:36', 96)} The core idea is regeneration over maintenance."),
]
BREAD_SECTIONS = [
    (0, "Part 1", f"{deep('plainvide00', '0:00:02', 2)} Block one content about sourdough starters."),
    (300, "Part 2", f"{deep('plainvide00', '0:05:10', 310)} Block two content about proofing times."),
]


def anchored_home(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr


def search_json(home, query):
    r = run_component("index", ["search", query, "--json"], home)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_link_plumbing_is_not_searchable(home):
    """`youtube` appears in every anchor and in nobody's prose: a single match
    is the index ranking the library by its own plumbing."""
    anchored_home(home)
    assert search_json(home, "youtube") == [], (
        "anchor URLs must not be indexable tokens"
    )
    assert search_json(home, "sourdough"), (
        "the prose after an anchor must remain searchable"
    )


def test_excerpts_open_with_prose_not_link_syntax(home):
    """The result already carries its deep link as a field (SPEC-index-002);
    the excerpt is for reading."""
    anchored_home(home)
    results = search_json(home, "regeneration")
    assert results, "no results for a term present in the prose"
    excerpt = results[0]["excerpt"]
    for plumbing in ("](https://", "&t=", "0:01:36"):
        assert plumbing not in excerpt, (
            f"the leading anchor must be stripped from chunk text:\n{excerpt!r}"
        )
    assert "regeneration" in excerpt


def test_a_pre_anchor_page_chunks_exactly_as_before(home):
    """Stripping is exact, not heuristic: a page with no paragraph anchors —
    every page written before SPEC-archive-002 — is untouched by it, prose
    brackets and all."""
    write_archive_page(
        home,
        PLAIN_META,
        [(0, "Part 1", "Plain prose [with brackets] and a t= mention, no anchor.")],
    )
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr
    results = search_json(home, "brackets")
    assert results, "unanchored prose must index exactly as it always has"
    assert "[with brackets]" in results[0]["excerpt"]
