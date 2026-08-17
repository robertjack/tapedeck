"""Durable evals: the acceptance gate (SPEC-wiki-002).

Boundary: `python -m wiki file <id>`; the maintainer seam faked through
config.toml, ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

The maintainer is an agent editing prose, so the wiki is only trustworthy if
every accepted commit was checked mechanically first. Each eval here hands the
run a maintainer that does honest work and breaks exactly one rule, and asks for
the same three things every time — exit 1, the violation named on stderr, and a
wiki byte-identical to the commit the run started from (wikilib.rejected).

The gate judges the whole wiki, not the diff: a page the maintainer never touched
can be broken by one it did, and a wiki that fails as a whole is not a wiki the
user should have to discover for themselves later.
"""

from wikilib import (
    ASK_REPORTS_A_FABRICATION,
    BREAKS_TWO_RULES,
    CITES_ANOTHER_VIDEO_ONLY,
    EDITS_THE_BRIEF,
    GOOD,
    LINKS_IN_THE_WRONG_CASE,
    LINKS_TO_NOTHING,
    NEXT,
    REWRITES_THE_LOG,
    rejected,
)


def test_the_brief_may_not_be_edited_by_the_maintainer(home, monkeypatch):
    """The conventions are the user's half of the arrangement. An agent that can
    rewrite its own instructions is not following them."""
    r = rejected(home, monkeypatch, EDITS_THE_BRIEF)
    assert "CLAUDE.md" in r.stderr, r.stderr


def test_a_sources_page_that_cites_only_another_video_is_rejected(home, monkeypatch):
    """The page exists to say what this video said and where. A citation of a
    real, verifiable, different video passes every other check in the gate — and
    still leaves the filed video unsourced."""
    r = rejected(home, monkeypatch, CITES_ANOTHER_VIDEO_ONLY)
    assert NEXT in r.stderr, (
        f"the violation names the video whose page fails to cite it: {r.stderr!r}"
    )


def test_a_wikilink_that_resolves_to_nothing_is_rejected(home, monkeypatch):
    """Consumption is plain files and [[wikilinks]], so a link that points at no
    page is the one defect nothing downstream can route around."""
    r = rejected(home, monkeypatch, LINKS_TO_NOTHING)
    assert "nonexistent-page" in r.stderr, (
        f"the unresolved target is named, or the user has to hunt for it: {r.stderr!r}"
    )


def test_wikilink_targets_are_resolved_case_sensitively(home, monkeypatch):
    """`[[Regeneration]]` beside `notes/regeneration.md` is a link that works in
    one reader and dangles in another. The gate reads it the strict way."""
    r = rejected(home, monkeypatch, LINKS_IN_THE_WRONG_CASE)
    assert "Regeneration" in r.stderr, r.stderr


def test_a_citation_ask_cannot_verify_is_rejected(home, monkeypatch):
    """ask's verdict is the gate's verdict, and its words are the ones reported:
    the rules for reading a citation live in one place (LESSON-0003)."""
    r = rejected(home, monkeypatch, GOOD, ask=ASK_REPORTS_A_FABRICATION)
    assert "unverifiable" in r.stderr, (
        f"what ask said about the link is what the user needs to see: {r.stderr!r}"
    )


def test_a_rewritten_log_is_rejected(home, monkeypatch):
    """Append-only is the whole value of the chronology: an entry that can be
    edited later is not a record of what happened. tapedeck writing the entries
    (SPEC-wiki-008) does not soften this — it is the *old* bytes that are
    protected, and an agent may still reach them."""
    r = rejected(home, monkeypatch, REWRITES_THE_LOG)
    assert "log.md" in r.stderr, r.stderr


def test_every_violation_is_reported_not_just_the_first(home, monkeypatch):
    """The maintainer gets one run per operation and the user pays for each. A
    gate that reports one fault at a time turns one rejection into several."""
    r = rejected(home, monkeypatch, BREAKS_TWO_RULES)
    assert "nonexistent-page" in r.stderr and "CLAUDE.md" in r.stderr, (
        f"both independent checks failed and both belong on stderr: {r.stderr!r}"
    )
