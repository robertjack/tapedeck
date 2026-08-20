"""Durable evals: a video that came off disk can be filed (SPEC-wiki-002 as
amended, SPEC-ingest-005).

Boundary: `python -m wiki file <id>`, seams faked exactly as wikilib fakes
them. The gate's filed-marker check asks whether a source page anchors itself
in its own recording — and the address of a local recording is its `file://`
path, not a YouTube watch URL. A gate that only recognizes youtube.com rejects
every filing of local footage, which is the failure this suite exists to catch.
"""

import wikilib
from conftest import add_video, run_component, set_maintainer, write_archive_page
from wikilib import ASK_VERIFIES, set_ask, subjects

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

# The archive page a local video renders: sections addressed by the file itself.
LOCAL_SECTIONS = [
    (0, "Intro", "Morning, everyone."),
    (300, "The Migration", "The migration finished overnight."),
]

# A maintainer filing local footage cites it the only way it can be cited.
FILES_A_LOCAL_VIDEO = wikilib.SH + f"""
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Filed from [the moment it matters]({LOCAL_URL}?t=300s).
MD
"""


def stocked_with_local(home):
    add_video(home, LOCAL_META, [{"start": 0.0, "end": 4.0, "text": "Morning."}])
    write_archive_page(home, LOCAL_META, LOCAL_SECTIONS)


def test_a_local_videos_filing_is_accepted(home, monkeypatch):
    """The whole point: a page citing `file://…` anchors itself in its own
    recording just as `watch?v=…` does, so the gate must accept it."""
    stocked_with_local(home)
    set_ask(monkeypatch, home, ASK_VERIFIES)
    set_maintainer(home, FILES_A_LOCAL_VIDEO)

    r = run_component("wiki", ["file", LOCAL_ID], home)
    assert r.returncode == 0, (
        f"a local video's filing must be accepted — the filed marker is a link to "
        f"the video's own address:\n{r.stdout}\n{r.stderr}"
    )
    wiki = home / "wiki"
    assert (wiki / "sources" / f"{LOCAL_ID}.md").is_file()
    assert subjects(wiki)[0] == f"wiki file {LOCAL_ID}"


def test_a_page_citing_the_wrong_video_is_still_rejected(home, monkeypatch):
    """The check stays narrow: accepting local addresses must not accept a page
    anchored in somebody else's recording."""
    stocked_with_local(home)
    set_ask(monkeypatch, home, ASK_VERIFIES)
    set_maintainer(
        home,
        wikilib.SH + """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Same ground as [the other one](file:///Users/somebody/Footage/other.mp4?t=10s).
MD
""",
    )
    r = run_component("wiki", ["file", LOCAL_ID], home)
    assert r.returncode == 1, (
        f"a page that never cites its own recording is not filed:\n{r.stdout}\n{r.stderr}"
    )


def test_the_task_quotes_the_address_form_the_video_actually_has(home, monkeypatch):
    """The maintainer is told how to address a moment so it never invents one.
    For local footage that instruction must name the file, not youtube.com."""
    stocked_with_local(home)
    set_ask(monkeypatch, home, ASK_VERIFIES)
    set_maintainer(home, wikilib.RECORDS_THE_TASK)
    run_component("wiki", ["file", LOCAL_ID], home)

    task = wikilib.task_given(home)
    assert LOCAL_PATH in task, (
        f"the task must quote the local video's own address form:\n{task}"
    )
    assert "watch?v=" not in task, (
        f"and must not offer a YouTube shape for footage that was never there:\n{task}"
    )
