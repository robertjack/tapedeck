"""Durable evals: wiki's selection says whose directory it is (SPEC-wiki-010).

Boundary: `python -m wiki sync --dry-run` and `python -m wiki lint --json`; neither
needs a maintainer, so nothing probabilistic runs here.

The same defect cli carried (system/evals/cli/test_staging_notes.py) lived here in
the same words: `.fetching-<id>-<random>` — ingest's download staging directory —
was reported as "not a video id — skipped, it is not tapedeck's". Two components
re-derived one rule and arrived at the same false sentence, which is the drift
LESSON-0003 exists to prevent; agreeing with each other did not make either right.

Held to the same bar as cli's, deliberately: the wording is this component's to
choose, but a download of a known video may not be called foreign, and the note
must name the video so a reader deciding whether to delete it knows which download
they would be deleting.
"""

from conftest import CHAPTERED_META, PLAIN_META, add_video, write_archive_page

from wikilib import CH_SECTIONS, wiki_sync

FOREIGN = ("not tapedeck's", "not tapedeck", "foreign", "stray", "someone else")

FILED = CHAPTERED_META["id"]
FETCHING = PLAIN_META["id"]
STAGING = f".fetching-{FETCHING}-a1b2c3"
STRANGER = "my-own-notes"


def staged(home, stranger=False):
    """One eligible video and one download in flight, as ingest leaves the tree
    mid-fetch. No maintainer is configured and none is needed: a rehearsal reads."""
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    staging = home / "library" / STAGING
    staging.mkdir(parents=True)
    (staging / "video.part").write_bytes(b"\x00partial download")
    if stranger:
        (home / "library" / STRANGER).mkdir(parents=True)


def staging_notes(stderr):
    """Only the lines about the staging directory — a stranger's note is allowed to
    read quite differently, and the last eval here depends on that."""
    return [line for line in stderr.splitlines() if STAGING in line or FETCHING in line]


def test_selection_does_not_call_our_own_download_foreign(home, monkeypatch):
    staged(home)
    r = wiki_sync(home, "--dry-run")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    lines = staging_notes(r.stderr)
    assert lines, f"selection said nothing identifiable about {STAGING}:\n{r.stderr}"
    said = " ".join(lines).lower()
    for claim in FOREIGN:
        assert claim not in said, (
            f"selection described a tapedeck download as {claim!r}:\n" + "\n".join(lines)
        )


def test_the_note_names_the_video_being_fetched(home, monkeypatch):
    staged(home)
    r = wiki_sync(home, "--dry-run")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert any(FETCHING in line for line in staging_notes(r.stderr)), (
        f"no note names the video being fetched ({FETCHING}):\n{r.stderr}"
    )


def test_a_download_in_flight_is_never_offered_as_filable(home, monkeypatch):
    """The rehearsal prints the ids it would file. A staging directory holds no
    archive page and no video yet, so it can never be one of them — and printing it
    would send the next sweep after work it cannot do (SPEC-wiki-003)."""
    staged(home)
    r = wiki_sync(home, "--dry-run")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert r.stdout.split() == [FILED], (
        f"the rehearsal must offer exactly the one eligible video:\n{r.stdout!r}"
    )


def test_a_directory_that_really_is_not_ours_may_still_be_called_one(home, monkeypatch):
    """The distinction restored here is between a stranger and our own — not a ban
    on naming strangers."""
    staged(home, stranger=True)
    r = wiki_sync(home, "--dry-run")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert STRANGER in r.stderr, (
        f"a directory that genuinely is not tapedeck's went unmentioned:\n{r.stderr}"
    )
