"""Durable evals: what first use of the wiki creates (SPEC-wiki-001).

Boundary: `python -m wiki file <id>`, library and wiki resolved from
$TAPEDECK_HOME; the maintainer seam faked through config.toml, ask's verification
through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

The wiki is scaffolded once and is the user's from then on. Two things follow, and
both are checked here: the scaffold has to exist before the maintainer is allowed
to touch anything — so a first operation that is rejected leaves a usable, empty
wiki rather than nothing — and the brief the scaffold writes is a default, not a
managed file. Everything wiki does not own it must not create either: config.toml
is cli's data, and a wiki that cannot find its seam says so rather than inventing
one.
"""

from conftest import set_maintainer
from wikilib import (
    DOES_NOTHING,
    FILED,
    GOOD,
    NEXT,
    filed,
    git,
    set_ask,
    stocked,
    subjects,
    wiki_file,
)

PINNED = ("CLAUDE.md", "index.md", "log.md")


def test_first_filing_creates_the_wiki_as_its_own_git_repo(home, monkeypatch):
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, GOOD)

    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    wiki = home / "wiki"
    for name in PINNED:
        assert (wiki / name).is_file(), f"the scaffold owes the wiki {name}"
    assert (wiki / "sources").is_dir() and (wiki / "notes").is_dir()

    top = git(wiki, "rev-parse", "--show-toplevel")
    assert top.returncode == 0 and top.stdout.strip().endswith("wiki"), (
        "the wiki is versioned as its own repository, not as a directory inside "
        f"whatever repo happens to contain the library: {top.stdout!r} {top.stderr!r}"
    )
    history = subjects(wiki)
    assert len(history) >= 2, (
        f"the scaffold is committed before the operation that caused it: {history}"
    )
    assert history[0].startswith("wiki file") and FILED in history[0], history
    assert not git(wiki, "status", "--porcelain").stdout.strip(), (
        "an accepted operation commits everything it wrote"
    )


def test_the_scaffold_survives_a_rejected_first_operation(home, monkeypatch):
    """The maintainer here does nothing at all, so the gate rejects the run for
    want of a sources page. The reset that follows goes back to the scaffold
    commit — the wiki the user can now write in by hand — never past it."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, DOES_NOTHING)

    r = wiki_file(home, FILED)
    assert r.returncode == 1, f"nothing was filed:\n{r.stdout}\n{r.stderr}"
    assert "sources" in r.stderr, (
        f"the missing sources page is the violation to report: {r.stderr!r}"
    )

    wiki = home / "wiki"
    for name in PINNED:
        assert (wiki / name).is_file(), f"the rollback destroyed the scaffold's {name}"
    assert (wiki / "CLAUDE.md").read_text().strip(), "the brief is scaffolded with defaults"
    assert (wiki / "index.md").read_text().strip() == "", "a fresh catalog is empty"
    assert (wiki / "log.md").read_text().strip() == "", "a fresh chronology is empty"
    assert len(subjects(wiki)) == 1, "the scaffold is one commit and it stands"
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_the_brief_is_scaffolded_once_and_then_belongs_to_the_user(home, monkeypatch):
    """Conventions are the user's to set, so a later operation may not restore,
    reformat or top up the brief it finds — and the chronology it appends to keeps
    everything already written there."""
    wiki = filed(home, monkeypatch)
    brief = wiki / "CLAUDE.md"
    mine = "# House rules\n\nOne page per idea. Dated notes only.\n"
    brief.write_text(mine)
    before_log = (wiki / "log.md").read_text()

    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert brief.read_text() == mine, (
        "a second filing rewrote the brief the user had made their own"
    )
    assert (wiki / "log.md").read_text().startswith(before_log), (
        "the chronology is appended to, never rebuilt"
    )


def test_a_missing_maintainer_command_exits_2_without_writing_config(home, monkeypatch):
    """config.toml belongs to cli; wiki only reads its seam out of it. With no
    seam configured there is nothing to run and no default worth guessing at —
    wiki says which key is missing and stops."""
    stocked(home)
    set_ask(monkeypatch, home)
    before = (home / "config.toml").read_text()

    r = wiki_file(home, FILED)
    assert r.returncode == 2, f"an unconfigured seam is a usage error:\n{r.stderr}"
    assert "maintainer_command" in r.stderr, (
        f"the message names the key the user has to set: {r.stderr!r}"
    )
    assert (home / "config.toml").read_text() == before, (
        "wiki wrote config.toml, which is cli's file to scaffold"
    )


def test_filing_never_touches_config_toml(home, monkeypatch):
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, GOOD)
    before = (home / "config.toml").read_text()

    assert wiki_file(home, FILED).returncode == 0
    assert (home / "config.toml").read_text() == before
