"""Durable evals: a citation may address a local video (SPEC-ask-001, amended;
contracts/ask-citations.md).

Boundary: `python -m ask verify` — text on stdin, library via $TAPEDECK_HOME.
Reuses test_verify's driver so both citation forms are read through exactly one
door. What is pinned here is that the promise does not weaken for a video that
came off disk: a local citation resolves to its entry by the path it names and
is then held to the same duration bound, with the same verdict, as a YouTube one.
"""

from conftest import add_video
from test_verify import verify

LOCAL_ID = "loc4lvide01"
LOCAL_PATH = "/Users/somebody/Footage/standup.mp4"
LOCAL_URL = f"file://{LOCAL_PATH}"
DURATION = 600

LOCAL_META = {
    "id": LOCAL_ID,
    "title": "standup",
    "channel": "",
    "upload_date": "2026-03-04",
    "duration_s": DURATION,
    "url": LOCAL_URL,
}


def local_library(home):
    add_video(home, LOCAL_META, [{"start": 0.0, "end": 4.0, "text": "Morning."}])


def test_a_local_citation_inside_the_video_verifies(home):
    local_library(home)
    r = verify(f"He says it [here]({LOCAL_URL}?t=95s).\n", home)
    assert r.returncode == 0, (
        f"a local deep link naming a library video at a real moment must verify:\n"
        f"{r.stdout}\n{r.stderr}"
    )


def test_a_local_citation_past_the_end_fails_like_any_other(home):
    local_library(home)
    r = verify(f"He says it [here]({LOCAL_URL}?t=99999s).\n", home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert r.stderr.strip(), "a rejection that says nothing cannot be acted on"


def test_a_local_citation_to_a_file_not_in_the_library_fails(home):
    """The fabrication case for local video: a plausible path nobody added."""
    local_library(home)
    r = verify("Covered [there](file:///Users/somebody/Footage/never-added.mp4?t=10s).\n", home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"


def test_a_local_citation_counts_as_a_citation(home):
    """`--require-citation` asks whether the text made a traceable claim at all;
    a local deep link is one, so a text carrying only local citations must not
    read as uncited."""
    local_library(home)
    r = verify(f"Everything rests on [this]({LOCAL_URL}?t=5s).\n", home, "--require-citation")
    assert r.returncode == 0, (
        f"a local citation is a citation — the guarantee is that a cited moment "
        f"exists, not that it lives on youtube.com:\n{r.stdout}\n{r.stderr}"
    )
