"""Durable evals: add closes each video's account in the user's terms, and
routes --verbose to the tool (SPEC-cli-012).

Boundary: the `tapedeck` executable, seams faked exactly as
test_add_collection.py fakes them. The close-out is the one stderr line naming
what was just added the way a person thinks of it — title, channel, duration —
and the --verbose pin is pure routing: a loud fixture fetcher's marker reaches
add's stderr only when the flag was passed, which proves the flag traveled to
ingest's boundary without the cli knowing what it means.
"""

from conftest import run_cli
from test_add_collection import (
    FETCH_ANY,
    FETCH_FAIL_MIDDLE,
    IDS,
    PLAYLIST,
    set_collection_pipeline,
)

VIDEO_A = IDS[0]
NOISE = "YTDLP-NOISE-MARKER-8842"

CHATTY_FETCH = FETCH_ANY.replace(
    "#!/bin/sh\n", f'#!/bin/sh\necho "{NOISE} downloading" >&2\n', 1
)


def test_each_added_video_gets_a_close_out_in_the_users_terms(home):
    """The collection fixture titles every video 'Video <id>' on 'Fixture
    Channel' at 720s — so the close-out is checkable word for word: title,
    channel, and the duration as h:mm:ss, one per completed video, on stderr
    and never stdout."""
    set_collection_pipeline(home)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    for vid in IDS:
        line = next(
            (l for l in r.stderr.splitlines() if f"Video {vid}" in l), None
        )
        assert line is not None, (
            f"no close-out names {vid}'s title on stderr:\n{r.stderr!r}"
        )
        assert "Fixture Channel" in line, f"the channel belongs in it: {line!r}"
        assert "0:12:00" in line, f"720s reads h:mm:ss in the layout's form: {line!r}"
        assert f"Video {vid}" not in r.stdout, "stdout still means what it meant"


def test_a_failed_fetch_points_at_the_manual_and_the_refresher(home):
    """The most common terminal moment a stranger hits is a fetch the platform
    broke; the error must end with the two commands that resolve it
    (SPEC-cli-013), in the cli's own line — ingest's is untouched."""
    set_collection_pipeline(home, FETCH_FAIL_MIDDLE)
    r = run_cli(["add", IDS[1]], home)
    assert r.returncode == 1
    assert "help manual" in r.stderr, (
        f"the failure names where the causes are explained:\n{r.stderr!r}"
    )
    assert "--refresh" in r.stderr, (
        f"the failure names the command that updates the tool:\n{r.stderr!r}"
    )


def test_verbose_travels_to_the_fetcher_and_absence_stays_quiet(home):
    set_collection_pipeline(home, CHATTY_FETCH)
    quiet = run_cli(["add", VIDEO_A], home)
    assert quiet.returncode == 0, quiet.stderr
    assert NOISE not in quiet.stderr, (
        f"without --verbose the tool's chatter must not reach add:\n{quiet.stderr!r}"
    )

    set_collection_pipeline(home, CHATTY_FETCH)
    loud = run_cli(["add", IDS[1], "--verbose"], home)
    assert loud.returncode == 0, loud.stderr
    assert NOISE in loud.stderr, (
        f"--verbose must travel to ingest's boundary whole:\n{loud.stderr!r}"
    )
