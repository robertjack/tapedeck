"""Durable evals: ask verify (SPEC-ask-005).

Boundary: `python -m ask verify [--video <id>] [--require-citation]` — answer/page
text on stdin, library via $TAPEDECK_HOME, exit 0 verified / 1 failed / 2 bad scope.
This is SPEC-ask-001's mechanical citation check published as a standalone boundary:
the same contracts/ask-citations.md reading, not a second one — wiki's acceptance
gate is the reader this exists for (LESSON-0003: citation grammar is ask's
vocabulary, consumed rather than re-derived). Several fixtures below are the exact
texts test_verification.py already runs through the librarian path; here they run
through the standalone verb instead, on the claim that both doors must agree.

`run_component` (conftest) has no seam for stdin, so `verify()` below drives the
module directly the same way conftest does — TAPEDECK_ASK_CMD override, same repo
cwd, same $TAPEDECK_HOME — with `input=` added for the text the verb reads.
"""

import os
import shlex
import subprocess
import sys

from conftest import CHAPTERED_META, PLAIN_META, REPO, TIMEOUT, add_video

# `duration_s: 0` is what ingest writes when the fetcher's info.json withheld the
# duration — the library knows the video, not how long it runs.
UNKNOWN_LEN_META = {
    "id": "unknownlen0",
    "title": "Fixture With No Duration",
    "channel": "Fixture Channel",
    "upload_date": "2026-03-03",
    "duration_s": 0,
    "url": "https://www.youtube.com/watch?v=unknownlen0",
}

# A markdown citation ending its sentence with a period — the contract's own example
# of a true citation that trailing prose must not convict.
VALID_CITATION = "It happens right [here](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s).\n"
# A bare link (no markdown parens to shield it) ending a sentence — the full stop
# must not be read into the video id.
BARE_LINK_ENDS_SENTENCE = "The build is covered at https://www.youtube.com/watch?v=dQw4w9WgXcQ.\n"
# The same shape with a moment on it, mid-sentence before a comma — the comma must
# not be read into the `t=` value.
BARE_LINK_BEFORE_COMMA = "See https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s, which says so.\n"
# A fabricated moment past the 720s fixture, wearing the same trailing full stop —
# the punctuation reading must not smuggle it past the bounds check.
OVERTIME_ENDS_SENTENCE = "It is settled at https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9999s.\n"
# A moment in a video whose duration nobody knows.
CITES_UNKNOWN_LENGTH = "Covered in [the talk](https://www.youtube.com/watch?v=unknownlen0&t=95s).\n"
# A video the library does not hold at all.
CITES_ABSENT_VIDEO = "Covered in [nothing](https://www.youtube.com/watch?v=nosuchvid00&t=95s).\n"
# A citation to a real, in-library video that is nonetheless not the scoped one.
CITES_OTHER_LIBRARY_VIDEO = "See [the bread one](https://www.youtube.com/watch?v=plainvide00&t=10s) too.\n"
# A confident claim carrying no deep link at all.
NO_CITATION = "A confident answer with no citations at all.\n"


def verify(text, home, *args):
    cmd = os.environ.get("TAPEDECK_ASK_CMD", f"{sys.executable} -m ask")
    return subprocess.run(
        [*shlex.split(cmd), "verify", *args],
        cwd=REPO,
        input=text,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env={
            **os.environ,
            "TAPEDECK_HOME": str(home),
            # installation-independent: components run from src/ with no packaging
            "PYTHONPATH": os.pathsep.join(
                [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        },
    )


def snapshot(home):
    """Every file's bytes and every directory under home. verify reads the library
    and reports (SPEC-ask-005: 'invokes no seam command and mutates nothing') — this
    is the eval's way of holding it to that."""
    files = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    dirs = {str(p.relative_to(home)) for p in home.rglob("*") if p.is_dir()}
    return files, dirs


def stocked(home):
    add_video(home, CHAPTERED_META)
    add_video(home, PLAIN_META)


# --- the basic verdict ---


def test_valid_in_bounds_citation_passes(home):
    stocked(home)
    r = verify(VALID_CITATION, home)
    assert r.returncode == 0, r.stderr


def test_out_of_bounds_timestamp_fails_with_a_violation_on_stderr(home):
    stocked(home)
    r = verify(OVERTIME_ENDS_SENTENCE, home)
    assert r.returncode == 1
    assert "9999" in r.stderr or "citation" in r.stderr.lower()


def test_citation_to_a_video_absent_from_the_library_fails(home):
    stocked(home)
    r = verify(CITES_ABSENT_VIDEO, home)
    assert r.returncode == 1
    assert "nosuchvid00" in r.stderr


# --- trailing sentence punctuation belongs to the sentence, not the URL ---


def test_bare_citation_ending_a_sentence_passes(home):
    stocked(home)
    r = verify(BARE_LINK_ENDS_SENTENCE, home)
    assert r.returncode == 0, r.stderr


def test_bare_citation_before_a_comma_passes(home):
    stocked(home)
    r = verify(BARE_LINK_BEFORE_COMMA, home)
    assert r.returncode == 0, r.stderr


# --- an unknown duration bounds nothing, but existence still does ---


def test_unknown_duration_waives_the_bounds_check(home):
    add_video(home, UNKNOWN_LEN_META)
    r = verify(CITES_UNKNOWN_LENGTH, home)
    assert r.returncode == 0, r.stderr


def test_unknown_duration_does_not_waive_the_exists_check(home):
    add_video(home, UNKNOWN_LEN_META)
    r = verify(CITES_ABSENT_VIDEO, home)
    assert r.returncode == 1
    assert "nosuchvid00" in r.stderr


# --- --video scoping tightens exactly as SPEC-ask-003 does ---


def test_video_scope_accepts_a_citation_to_the_scoped_video(home):
    stocked(home)
    r = verify(VALID_CITATION, home, "--video", CHAPTERED_META["id"])
    assert r.returncode == 0, r.stderr


def test_video_scope_rejects_a_citation_to_a_different_library_video(home):
    stocked(home)
    r = verify(CITES_OTHER_LIBRARY_VIDEO, home, "--video", CHAPTERED_META["id"])
    assert r.returncode == 1, "plainvide00 is in the library, but not the scope"
    assert "plainvide00" in r.stderr


def test_video_scope_with_an_id_not_in_the_library_exits_2(home):
    stocked(home)
    r = verify(VALID_CITATION, home, "--video", "nosuchvid00")
    assert r.returncode == 2
    assert "nosuchvid00" in r.stderr


# --- --require-citation ---


def test_uncited_text_passes_without_require_citation(home):
    stocked(home)
    r = verify(NO_CITATION, home)
    assert r.returncode == 0, r.stderr


def test_uncited_text_fails_with_require_citation(home):
    stocked(home)
    r = verify(NO_CITATION, home, "--require-citation")
    assert r.returncode == 1


def test_cited_text_still_passes_with_require_citation(home):
    stocked(home)
    r = verify(VALID_CITATION, home, "--require-citation")
    assert r.returncode == 0, r.stderr


# --- verify only reads ---


def test_verify_never_writes_to_the_library(home):
    stocked(home)
    before = snapshot(home)
    r = verify(OVERTIME_ENDS_SENTENCE, home)  # a failing run must not mutate either
    assert r.returncode == 1
    assert snapshot(home) == before
