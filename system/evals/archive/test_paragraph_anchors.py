"""Durable evals: every paragraph opens with its own deep link
(SPEC-archive-002).

Boundary: `python -m archive render <id>`, library via $TAPEDECK_HOME, exactly
as test_render.py drives it. What is pinned here: each paragraph's line begins
with `[h:mm:ss](deep-link) ` carrying the paragraph's *first segment's* start —
never the section's start, never an interpolation — while the section headings
and everything test_render.py pins stay exactly as they are.
"""

from conftest import (
    CHAPTERED_META,
    CHAPTERED_SEGMENTS,
    PLAIN_META,
    PLAIN_SEGMENTS,
    add_video,
    run_component,
)


def rendered(home, meta, segments):
    add_video(home, meta, segments)
    r = run_component("archive", ["render", meta["id"]], home)
    assert r.returncode == 0, r.stderr
    return (home / "archive" / f"{meta['id']}.md").read_text()


def anchor(video_id, hms, seconds):
    return f"\n[{hms}](https://www.youtube.com/watch?v={video_id}&t={seconds}s) "


def test_chapterless_paragraphs_carry_their_first_segments_start(home):
    """The five-minute fallback's whole problem: three claims, one t=. Each
    fixture block is one paragraph whose first segment starts *after* its
    section heading (2s, 310s, 640s vs headings at 0s, 300s, 600s), so an
    implementation that reuses the section start fails here rather than
    passing by coincidence."""
    content = rendered(home, PLAIN_META, PLAIN_SEGMENTS)
    assert anchor("plainvide00", "0:00:02", 2) + "Block one content" in content
    assert anchor("plainvide00", "0:05:10", 310) + "Block two content" in content
    assert anchor("plainvide00", "0:10:40", 640) + "Block three content" in content


def test_chaptered_paragraphs_are_anchored_the_same_way(home):
    """Chapters change the sections, not the paragraphs' addresses: the Core
    Idea chapter is headed at 95s but its only segment starts at 96s, and the
    anchor must say 96."""
    content = rendered(home, CHAPTERED_META, CHAPTERED_SEGMENTS)
    assert anchor("dQw4w9WgXcQ", "0:00:00", 0) + "Welcome to the fixture show." in content
    assert anchor("dQw4w9WgXcQ", "0:01:36", 96) + "The core idea" in content
    assert anchor("dQw4w9WgXcQ", "0:10:12", 612) + "Thanks for watching" in content


def test_one_anchor_per_paragraph_and_prose_is_unmodified(home):
    """The anchor is the paragraph's address, not a decoration scattered
    through it: exactly one leading anchor per paragraph line, and the prose
    after it is the transcript's, word for word."""
    content = rendered(home, PLAIN_META, PLAIN_SEGMENTS)
    paragraph_lines = [
        line
        for line in content.splitlines()
        if line and not line.startswith(("#", "-", "id:", "title:", "channel:",
                                         "upload_date:", "duration_s:", "url:"))
        and "Block" in line
    ]
    assert len(paragraph_lines) == 3
    for line in paragraph_lines:
        assert line.startswith("["), f"a paragraph must open with its anchor: {line!r}"
        assert line.count("](https://") == 1, (
            f"exactly one anchor, at the head, never inline: {line!r}"
        )
        prose = line.split(") ", 1)[1]
        assert prose.startswith("Block"), f"prose must follow the anchor unmodified: {line!r}"
