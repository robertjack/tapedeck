"""Durable evals: the help verb (SPEC-cli-005).

Boundary: the `tapedeck` executable. Every run here pipes stdout, so these
tests pin the non-TTY contract: plain bytes, no escape sequences, no pager.
The TTY niceties (ANSI, $PAGER) are spec-side behavior.
"""

import os
import re

from conftest import REPO, run_cli

VERB_ROW = re.compile(r"\| `tapedeck ([a-z-]+)")


def test_help_prints_a_one_screen_tour(home):
    r = run_cli(["help"], home)
    assert r.returncode == 0, r.stderr
    for verb in ("add", "search", "ask", "list", "show", "retranscribe"):
        assert verb in r.stdout, f"tour must name the everyday verb {verb!r}"
    assert "tapedeck add" in r.stdout, "the tour teaches by example"
    assert len(r.stdout.splitlines()) <= 45, "the no-argument tour is one screen"
    assert "\x1b" not in r.stdout, "piped output carries no escape sequences"


def test_help_verb_shows_usage_and_a_worked_example(home):
    r = run_cli(["help", "add"], home)
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout
    assert "--force" in r.stdout
    assert "tapedeck add" in r.stdout, "per-verb help includes a worked example"


def test_help_manual_piped_is_the_manual_verbatim(home, monkeypatch):
    monkeypatch.setenv("PAGER", "/bin/false")  # a pager invocation would fail loudly
    r = run_cli(["help", "manual"], home)
    assert r.returncode == 0, r.stderr
    assert r.stdout == (REPO / "MANUAL.md").read_text(encoding="utf-8"), (
        "piped `help manual` is byte-identical to MANUAL.md"
    )
    assert "\x1b" not in r.stdout


def test_help_unknown_topic_exits_2_naming_what_it_knows(home):
    r = run_cli(["help", "bogus"], home)
    assert r.returncode == 2
    assert "manual" in (r.stdout + r.stderr), "the error should name the known topics"


def test_manual_covers_the_whole_surface():
    surface = (REPO / "system" / "contracts" / "cli-surface.md").read_text(encoding="utf-8")
    manual = (REPO / "MANUAL.md").read_text(encoding="utf-8")
    verbs = set(VERB_ROW.findall(surface))
    assert verbs, "no verbs parsed from the surface contract"
    for verb in verbs:
        assert verb in manual, f"MANUAL.md has drifted: {verb!r} is on the surface but undocumented"
