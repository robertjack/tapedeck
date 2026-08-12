"""Durable evals: archive renderer (SPEC-archive-001).

Boundary: `python -m archive render <id>` / `python -m archive render-all`,
library via $TAPEDECK_HOME. Pure render of meta.json + transcript.json into
archive/<id>.md — deterministic to the byte.
"""

from conftest import (
    CHAPTERED_META,
    CHAPTERED_SEGMENTS,
    PLAIN_META,
    PLAIN_SEGMENTS,
    add_video,
    run_component,
)


def render(home, *args):
    return run_component("archive", ["render", *args], home)


def test_render_writes_frontmatter_and_chapter_sections(home):
    add_video(home, CHAPTERED_META, CHAPTERED_SEGMENTS)
    r = render(home, "dQw4w9WgXcQ")
    assert r.returncode == 0, r.stderr
    page = home / "archive" / "dQw4w9WgXcQ.md"
    assert page.is_file()
    content = page.read_text()
    for needle in (
        "id: dQw4w9WgXcQ",
        "title:",
        "Test Video: Building Things",
        "channel: Fixture Channel",
        "upload_date: 2026-01-15",
        "duration_s: 720",
        "url:",
    ):
        assert needle in content, f"frontmatter missing {needle!r}"
    # chapter headings carry [h:mm:ss](deep-link) per the layout contract
    assert "[0:00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s)" in content
    assert "[0:01:35](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s)" in content
    assert "[0:10:10](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=610s)" in content
    for title in ("Intro", "The Core Idea", "Wrap Up"):
        assert title in content


def test_segments_land_in_their_chapters(home):
    add_video(home, CHAPTERED_META, CHAPTERED_SEGMENTS)
    render(home, "dQw4w9WgXcQ")
    content = (home / "archive" / "dQw4w9WgXcQ.md").read_text()
    core = content.index("The Core Idea")
    wrap = content.index("Wrap Up")
    line = content.index("The core idea is regeneration over maintenance.")
    assert core < line < wrap, "segment text not placed inside its chapter section"


def test_five_minute_blocks_without_chapters(home):
    add_video(home, PLAIN_META, PLAIN_SEGMENTS)
    r = render(home, "plainvide00")
    assert r.returncode == 0, r.stderr
    content = (home / "archive" / "plainvide00.md").read_text()
    assert "[0:00:00](https://www.youtube.com/watch?v=plainvide00&t=0s)" in content
    assert "[0:05:00](https://www.youtube.com/watch?v=plainvide00&t=300s)" in content
    assert "[0:10:00](https://www.youtube.com/watch?v=plainvide00&t=600s)" in content
    first = content.index("sourdough starters")
    second = content.index("proofing times")
    third = content.index("scoring loaves")
    assert first < content.index("&t=300s") < second < content.index("&t=600s") < third


def test_rerender_is_byte_identical(home):
    add_video(home, CHAPTERED_META, CHAPTERED_SEGMENTS)
    render(home, "dQw4w9WgXcQ")
    first = (home / "archive" / "dQw4w9WgXcQ.md").read_bytes()
    r = render(home, "dQw4w9WgXcQ")
    assert r.returncode == 0
    assert (home / "archive" / "dQw4w9WgXcQ.md").read_bytes() == first


def test_render_all_covers_every_ready_video(home):
    add_video(home, CHAPTERED_META, CHAPTERED_SEGMENTS)
    add_video(home, PLAIN_META, PLAIN_SEGMENTS)
    r = run_component("archive", ["render-all"], home)
    assert r.returncode == 0, r.stderr
    assert (home / "archive" / "dQw4w9WgXcQ.md").is_file()
    assert (home / "archive" / "plainvide00.md").is_file()


def test_missing_transcript_fails_cleanly(home):
    add_video(home, CHAPTERED_META, segments=None)
    r = render(home, "dQw4w9WgXcQ")
    assert r.returncode == 1
    assert "transcript" in r.stderr.lower()
    assert not (home / "archive" / "dQw4w9WgXcQ.md").exists()


def test_unknown_video_id_is_usage_error(home):
    r = render(home, "nosuchvid00")
    assert r.returncode in (1, 2)
    assert "nosuchvid00" in r.stderr
