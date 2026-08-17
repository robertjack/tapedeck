"""Durable evals: a staging directory is not a stranger (SPEC-cli-010, SPEC-ingest-003).

Boundary: the `tapedeck` executable, library via $TAPEDECK_HOME, transcriber seam
faked through config.toml.

`ingest` downloads into `library/.fetching-<id>-<random>/` and renames it into
place, so while a fetch runs that directory *is* the fetch. Every sweep that walks
`library/` meets one eventually, and until 2026-08-17 the retranscribe sweep said
of it: "not a video id — skipped, it is not tapedeck's".

It is tapedeck's. A reader who believed that sentence recommended `rm -rf` on a
directory with a live yt-dlp inside it, and the library survived because a sandbox
happened to refuse the command — not because anything here stopped it.

These evals pin the falsehood out, not a replacement wording. The note may say
whatever the component judges useful; what it may not do is call a download of a
known video foreign, and it must name the video, so a reader deciding whether to
delete it knows what they would be deleting. Note the scope of every assertion is
the line about the *staging* directory: a note about a directory that genuinely is
not ours may still say so, and the last eval here holds that door open.
system/evals/wiki/test_staging.py holds wiki's selection to the same bar — one
library, two readers, and they must not disagree about whose directory it is.
"""

from conftest import CHAPTERED_META, PLAIN_META, add_video, set_transcriber

from conftest import run_cli

MODEL = "fixture/whisper-0"  # matches add_video's transcript label: nothing superseded
NOOP_TRANSCRIBER = "#!/bin/sh\nexit 1\n"  # never invoked; a dry run selects nothing

# The claims a note about our own staging directory must not make.
FOREIGN = ("not tapedeck's", "not tapedeck", "foreign", "stray", "someone else")

FETCHING = PLAIN_META["id"]  # the video whose download is in flight
STAGING = f".fetching-{FETCHING}-a1b2c3"
STRANGER = "my-own-notes"


def staged(home, stranger=False):
    """A library holding one finished entry and one download in flight, as ingest
    leaves the tree mid-fetch: the staging directory carries a partial `video.part`,
    which is what a running yt-dlp has actually written so far. `stranger` adds a
    directory that really is the user's own, for the contrast case."""
    set_transcriber(home, NOOP_TRANSCRIBER, model=MODEL)
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Filed."}])
    staging = home / "library" / STAGING
    staging.mkdir(parents=True)
    (staging / "video.part").write_bytes(b"\x00partial download")
    if stranger:
        (home / "library" / STRANGER).mkdir(parents=True)
    return staging


def sweep(home):
    r = run_cli(["retranscribe", "--dry-run"], home)
    assert r.returncode == 0, f"retranscribe --dry-run must run:\n{r.stdout}\n{r.stderr}"
    return r


def staging_notes(stderr):
    """Only the lines the sweep printed about the staging directory. Scoping matters:
    the assertions below are about how *our* directory is described, and a note about
    a stranger's is allowed to read quite differently."""
    return [line for line in stderr.splitlines() if STAGING in line or FETCHING in line]


def test_the_sweep_does_not_call_our_own_download_foreign(home):
    """The sentence that cost a live download its life, pinned out."""
    staged(home)
    r = sweep(home)
    lines = staging_notes(r.stderr)
    assert lines, f"the sweep said nothing identifiable about {STAGING}:\n{r.stderr}"
    said = " ".join(lines).lower()
    for claim in FOREIGN:
        assert claim not in said, (
            f"the sweep described a tapedeck download as {claim!r}:\n" + "\n".join(lines)
        )


def test_the_note_names_the_video_being_fetched(home):
    """A reader deciding whether to delete a directory needs to know it belongs to a
    download, and to which one. A note that says only "skipped" invites tidying up."""
    staged(home)
    r = sweep(home)
    lines = staging_notes(r.stderr)
    assert any(FETCHING in line for line in lines), (
        f"no note names the video being fetched ({FETCHING}), so a reader cannot tell "
        f"which download this directory is:\n{r.stderr}"
    )


def test_a_download_in_flight_is_never_selected_for_work(home):
    """Unchanged by the wording fix, and worth pinning while we are here: a staging
    directory has no transcript to supersede, and selecting one would mean the sweep
    never reaches a no-op (SPEC-cli-004)."""
    staged(home)
    r = sweep(home)
    assert STAGING not in r.stdout, (
        f"the sweep selected a download in flight as work to redo:\n{r.stdout}"
    )


def test_a_directory_that_really_is_not_ours_may_still_be_called_one(home):
    """The fix is not "stop describing strangers". A directory of the user's own under
    library/ is still theirs and still skipped, and the note about it is free to say
    so — the distinction this clause restores is between that and our own."""
    staged(home, stranger=True)
    r = sweep(home)
    assert STRANGER in r.stderr, (
        f"a directory that genuinely is not tapedeck's went unmentioned:\n{r.stderr}"
    )
