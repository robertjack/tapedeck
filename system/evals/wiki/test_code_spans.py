"""Durable evals: a page may write about wiki links (SPEC-wiki-011).

Boundary: `python -m wiki file <id>` and `python -m wiki lint --json`; the
maintainer seam faked through config.toml, ask through $TAPEDECK_ASK_CMD.

The gate resolved every `[[target]]` in raw text, so a page that *quoted* the
syntax had its example read as a claim. On 2026-08-17 an apply-mode tend edited
seven notes and a source page, wrote a chronology entry describing the linking
discipline it had just worked on, and was rejected whole for the `[[wikilink]]`
inside that sentence — twenty minutes and a real bill discarded because a wiki
about harnesses may not mention its own syntax.

These evals hold both halves: code spans and fenced blocks are literal text, and
a bare dangling link outside code is still the defect it always was. `lint` is held
to the same rule as the gate, because a linter that sent the user to fix a page the
gate accepts would be worse than no linter (SPEC-wiki-004).

The fakes append to `notes/proofing.md`, which WRITES_THE_PAGES has already created,
and use a quoted heredoc so the shell leaves backticks alone.
"""

from conftest import run_component

from wikilib import (
    NEXT,
    SH,
    WRITES_THE_PAGES,
    accepted,
    rejected,
    set_ask,
    set_maintainer,
    stocked,
    wiki_file,
)

MISSING = "a-page-that-does-not-exist"

# Inline code: the sentence the tend was rejected for, in its general form.
QUOTES_THE_SYNTAX = SH + WRITES_THE_PAGES + f"""
cat >> "notes/proofing.md" <<'MD'

Pages point at each other with `[[{MISSING}]]`, which is markdown code and names
no page at all.
MD
"""

# A fenced block: the other way a page explains the form.
FENCES_AN_EXAMPLE = SH + WRITES_THE_PAGES + f"""
cat >> "notes/proofing.md" <<'MD'

```
See also [[{MISSING}]].
```
MD
"""

# The same target, in ordinary prose. Still a claim, still a defect.
CLAIMS_IT_IN_PROSE = SH + WRITES_THE_PAGES + f"""
cat >> "notes/proofing.md" <<'MD'

See also [[{MISSING}]].
MD
"""


def test_a_quoted_wiki_link_is_not_a_link(home, monkeypatch):
    """Backticks mean the literal characters. This is the sentence that cost a tend
    its work."""
    r, _ = accepted(home, monkeypatch, QUOTES_THE_SYNTAX)
    assert MISSING not in r.stderr, (
        f"an example in backticks was read as a claim:\n{r.stderr}"
    )


def test_a_fenced_wiki_link_is_not_a_link(home, monkeypatch):
    accepted(home, monkeypatch, FENCES_AN_EXAMPLE)


def test_a_dangling_link_in_prose_is_still_rejected(home, monkeypatch):
    """The exemption is for code, not for carelessness. Same target, no backticks:
    a page the writer believed existed is still the one defect nothing reading the
    wiki afterwards can route around."""
    r = rejected(home, monkeypatch, CLAIMS_IT_IN_PROSE)
    assert MISSING in r.stderr, (
        f"the unresolved target must still be named:\n{r.stderr}"
    )


def test_lint_reads_code_the_same_way_the_gate_does(home, monkeypatch):
    """A linter that failed a page the gate accepted would send the user to fix
    nothing (SPEC-wiki-004). Both sides read the same rule or the pair is useless."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, QUOTES_THE_SYNTAX)
    assert wiki_file(home, NEXT).returncode == 0

    r = run_component("wiki", ["lint"], home)
    assert r.returncode == 0, (
        f"lint failed a wiki the gate had just accepted:\n{r.stdout}\n{r.stderr}"
    )
    assert MISSING not in r.stdout + r.stderr, (
        f"lint reported a quoted example as a broken link:\n{r.stdout}\n{r.stderr}"
    )


def test_a_rejected_run_still_prints_what_it_was_attempting(home, monkeypatch):
    """A rejection loses the work by design. Losing the agent's account of it as well
    is the difference between a wasted run and one a person can learn from — and the
    tend that prompted this clause left nothing behind but file paths in a feed."""
    r = rejected(home, monkeypatch, CLAIMS_IT_IN_PROSE + "\necho 'I linked the two proofing notes together.'\n")
    said = r.stdout + r.stderr
    assert "proofing notes together" in said, (
        f"the maintainer said what it was doing and the rejection threw it away:\n{said}"
    )
    assert MISSING in r.stderr, (
        "the reasons still reach the user, and still decide the exit code"
    )
