"""Durable evals: how ask reads a citation before judging it (SPEC-ask-001).

Boundary: `python -m ask run "<question>"` in librarian mode, library via
$TAPEDECK_HOME, seam pinned by conftest.set_librarian.

Two ways verification can be wrong about the same link, both covered here: prose
punctuation read as part of the URL (contracts/ask-citations.md, "Where a citation's
URL ends"), and `duration_s: 0` read as a real duration rather than as an unknown one
("Unknown durations"). A verifier that convicts true citations is as broken as one
that excuses false ones.
"""

from conftest import CHAPTERED_META, add_video, run_component, set_librarian

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

# A real citation, written bare at the end of a sentence — no markdown parens to
# shield the URL from the full stop that closes the prose.
LIBRARIAN_BARE_LINK_ENDS_SENTENCE = """#!/bin/sh
cat > /dev/null
printf 'The build is covered at https://www.youtube.com/watch?v=dQw4w9WgXcQ.\\n'
"""
# The same shape with a moment on it, mid-sentence before a comma.
LIBRARIAN_BARE_LINK_BEFORE_COMMA = """#!/bin/sh
cat > /dev/null
printf 'See https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s, which says so.\\n'
"""
# A fabricated moment — 9999s is past the 720s fixture — wearing the same full stop.
LIBRARIAN_OVERTIME_ENDS_SENTENCE = """#!/bin/sh
cat > /dev/null
printf 'It is settled at https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9999s.\\n'
"""
# A moment in the video whose duration nobody knows.
LIBRARIAN_CITES_UNKNOWN_LENGTH = """#!/bin/sh
cat > /dev/null
printf 'Covered in [the talk](https://www.youtube.com/watch?v=unknownlen0&t=95s).\\n'
"""
# A video the library does not hold — unknown durations must not excuse this.
LIBRARIAN_CITES_ABSENT_VIDEO = """#!/bin/sh
cat > /dev/null
printf 'Covered in [nothing](https://www.youtube.com/watch?v=nosuchvid00&t=95s).\\n'
"""


def ask(home, *args):
    return run_component("ask", ["run", *args], home)


def stocked(home, meta=CHAPTERED_META):
    add_video(home, meta, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])


# --- trailing punctuation is prose, not URL ---


def test_bare_citation_ending_a_sentence_is_not_a_fabrication(home):
    """`watch?v=<id>.` cites <id>; the full stop belongs to the sentence."""
    stocked(home)
    set_librarian(home, LIBRARIAN_BARE_LINK_ENDS_SENTENCE)
    r = ask(home, "what is this about")
    assert r.returncode == 0, r.stderr
    assert "dQw4w9WgXcQ" in r.stdout


def test_bare_citation_before_a_comma_is_not_a_fabrication(home):
    stocked(home)
    set_librarian(home, LIBRARIAN_BARE_LINK_BEFORE_COMMA)
    r = ask(home, "what is this about")
    assert r.returncode == 0, r.stderr


def test_trailing_punctuation_does_not_smuggle_a_timestamp_past_the_bounds(home):
    """A `t=` the parser cannot read is not a link that claims no moment."""
    stocked(home)
    set_librarian(home, LIBRARIAN_OVERTIME_ENDS_SENTENCE)
    r = ask(home, "what is this about")
    assert r.returncode == 1, "9999s is past the end of a 720s video, full stop or not"
    assert "9999" in r.stderr or "citation" in r.stderr.lower()


# --- an unknown duration bounds nothing ---


def test_unknown_duration_cannot_disprove_a_moment(home):
    stocked(home, UNKNOWN_LEN_META)
    set_librarian(home, LIBRARIAN_CITES_UNKNOWN_LENGTH)
    r = ask(home, "what is this about")
    assert r.returncode == 0, r.stderr
    assert "unknownlen0" in r.stdout


def test_unknown_duration_still_requires_the_video_to_exist(home):
    stocked(home, UNKNOWN_LEN_META)
    set_librarian(home, LIBRARIAN_CITES_ABSENT_VIDEO)
    r = ask(home, "what is this about")
    assert r.returncode == 1
    assert "nosuchvid00" in r.stderr
