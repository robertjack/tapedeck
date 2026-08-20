"""Durable evals: a local video's page addresses that file (SPEC-archive-001 as
amended, SPEC-ingest-005, contracts/library-layout.md).

Boundary: `python -m archive render <id>`, library via $TAPEDECK_HOME. The
layout contract has one deep-link rule — the video's own `url` carrying a `t=`
offset — so this suite is the proof that archive follows the rule rather than
hard-coding the host it was first written against. A YouTube video's page is
unchanged, which test_render.py pins; here the same renderer meets a video that
came off disk.
"""

from conftest import add_video, run_component

LOCAL_ID = "loc4lvide01"
LOCAL_PATH = "/Users/somebody/Footage/standup.mp4"
LOCAL_URL = f"file://{LOCAL_PATH}"

LOCAL_META = {
    "id": LOCAL_ID,
    "title": "standup",
    "channel": "",
    "upload_date": "2026-03-04",
    "duration_s": 720,
    "url": LOCAL_URL,
}
SEGMENTS = [
    {"start": 2.0, "end": 6.0, "text": "Yesterday I finished the migration."},
    {"start": 310.0, "end": 316.0, "text": "Today I am on the flaky test."},
]


def rendered(home):
    add_video(home, LOCAL_META, SEGMENTS)
    r = run_component("archive", ["render", LOCAL_ID], home)
    assert r.returncode == 0, r.stderr
    return (home / "archive" / f"{LOCAL_ID}.md").read_text()


def test_headings_and_anchors_address_the_file(home):
    content = rendered(home)
    assert f"[0:00:00]({LOCAL_URL}?t=0s)" in content, (
        f"a section heading addresses the video's own url:\n{content}"
    )
    assert f"[0:00:02]({LOCAL_URL}?t=2s)" in content, (
        f"and so does a paragraph anchor, at its own first segment:\n{content}"
    )
    assert f"[0:05:10]({LOCAL_URL}?t=310s)" in content


def test_no_youtube_address_appears_for_a_local_video(home):
    """The failure this exists to catch is a page that quietly points at
    youtube.com/watch?v=<id> for footage that was never on YouTube — a link
    that resolves to somebody else's video, or to nothing."""
    content = rendered(home)
    assert "youtube.com" not in content, (
        f"a local video's page must not address youtube:\n{content}"
    )


def test_the_byline_omits_the_empty_channel(home):
    """A local file has no publisher, so meta carries an empty channel; the
    byline must read as a byline rather than as a leading separator."""
    content = rendered(home)
    byline = next(line for line in content.splitlines() if "2026-03-04" in line)
    assert not byline.startswith("·") and " ·  · " not in byline, (
        f"empty channel must not leave a dangling separator: {byline!r}"
    )
