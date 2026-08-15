"""Durable evals: `rebuild` (SPEC-wiki-005).

Boundary: `python -m wiki rebuild [--yes]`; maintainer seam faked through
config.toml, ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

Every other layer of tapedeck is regenerable and therefore disposable
(SPEC-core-002): `reindex` throws the database away because nothing is lost by
throwing it away. The wiki is the one layer that is not — it is written by an
agent reading a brief, in an order that shaped what it wrote, with the user's own
hand-edits mixed in (SPEC-wiki-001) — so the same verb here destroys work that
cannot be re-derived. Two things follow, and this suite is about both.

The first is consent, in `setup`'s mold (SPEC-cli-008): without `--yes` the
command executes nothing at all. It says which wiki it resolved, what would be
removed, and what it would refile, and stops — a preview a user can read before
agreeing to it, not a confirmation they clicked through.

The second is that git is the safety net rather than the paperwork. The reset is
one commit, so the wiki as it stood is one `git show` away forever; the user's
pending edits are committed before it, so nothing typed by hand is lost to it;
and `CLAUDE.md` and the chronology survive, because the brief is the whole reason
the second wiki will be better than the first and a log that a rebuild could
erase is not a record of anything.
"""

import re

from conftest import set_maintainer
from wikilib import (
    MUST_NOT_RUN,
    RECORDS_EACH_ID,
    SWEEP_ORDER,
    git,
    links_to_nothing_for,
    log_entries,
    maintainer_ids,
    set_ask,
    snapshot,
    subjects,
    summary_line,
    unfiled_library,
    wiki_file,
    wiki_rebuild,
)

BROKEN = "middle00002"  # the one video whose refiling the gate rejects


def file_everything(home, monkeypatch, maintainer=RECORDS_EACH_ID):
    """The wiki every rebuild here is measured against: the whole fixture library
    filed into it one video at a time, through the operation round one already
    pins. Returns the wiki directory, with the record of the maintainer's
    invocations cleared so the rebuild's own are the only ones in it."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, maintainer)
    for vid in SWEEP_ORDER:
        r = wiki_file(home, vid)
        assert r.returncode == 0, f"the fixture wiki must file cleanly:\n{r.stdout}\n{r.stderr}"
    (home / "maintainer-ids").unlink()
    return home / "wiki"


def refile_order(text):
    """The ids the preview says it would refile, in the order it says them. Read
    from each id's last mention: the reset it describes first may name the same
    pages in an order of its own, and the promise under test is the order the
    refiling would happen in."""
    seen = {}
    for position, token in enumerate(re.findall(r"[A-Za-z0-9_-]{11}", text)):
        if token in SWEEP_ORDER:
            seen[token] = position
    return sorted(seen, key=seen.get)


def commit_named(wiki, subject):
    """The sha of the one commit with this subject."""
    lines = git(wiki, "log", "--format=%H %s").stdout.splitlines()
    matches = [line.split(" ", 1)[0] for line in lines if line.split(" ", 1)[1] == subject]
    assert len(matches) == 1, f"expected one {subject!r} commit:\n" + "\n".join(lines)
    return matches[0]


# --- the preview -------------------------------------------------------------


def test_a_preview_without_yes_executes_nothing(home, monkeypatch):
    """Consent is the specification: the user has to be able to read what would
    happen without any of it having happened yet. Nothing is reset, nothing is
    filed, nothing is committed — not even the edit sitting in the working tree."""
    wiki = file_everything(home, monkeypatch)
    (wiki / "notes" / "mine.md").write_text("Mine: pending, and none of the preview's business.\n")
    before, history = snapshot(wiki), subjects(wiki)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_rebuild(home)
    assert r.returncode == 0, f"a preview that changed nothing did not fail:\n{r.stderr}"
    assert not (home / "maintainer-ran").exists(), "the maintainer was invoked anyway"

    assert str(wiki) in r.stdout, (
        f"the wiki about to be destroyed is named by its resolved path, because a "
        f"surprising $TAPEDECK_HOME is exactly what this preview is for: {r.stdout!r}"
    )
    assert "sources" in r.stdout and "notes" in r.stdout, (
        f"the preview says what the reset would remove: {r.stdout!r}"
    )
    assert refile_order(r.stdout) == SWEEP_ORDER, (
        f"and what it would refile, in the order it would do it: {r.stdout!r}"
    )

    assert snapshot(wiki) == before, "the preview wrote to the wiki"
    assert subjects(wiki) == history, (
        "the preview committed something — even the user-edits commit is part of "
        "the rebuild the user has not agreed to yet"
    )


def test_a_preview_needs_no_maintainer(home, monkeypatch):
    """It spends no agent invocation, so an unconfigured seam cannot stop it: a
    user deciding whether to rebuild is exactly the user who may not have the
    agent set up yet."""
    wiki = file_everything(home, monkeypatch)
    (home / "config.toml").write_text("# no seam configured\n")
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_rebuild(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert refile_order(r.stdout) == SWEEP_ORDER, r.stdout
    assert snapshot(wiki) == before and subjects(wiki) == history


# --- the rebuild -------------------------------------------------------------


def test_yes_resets_the_wiki_and_refiles_the_library(home, monkeypatch):
    """The whole arrangement in one run: what is destroyed, what survives it, and
    where the destroyed version went."""
    wiki = file_everything(home, monkeypatch)

    brief = wiki / "CLAUDE.md"
    house_rules = "# House rules\n\nOne page per idea. Dated notes only.\n"
    brief.write_text(house_rules)
    hand = wiki / "notes" / "mine.md"
    marker = "Mine: written by hand, and no machine's to lose.\n"
    hand.write_text(marker)
    old_log = (wiki / "log.md").read_text()
    old_page = (wiki / "sources" / f"{SWEEP_ORDER[0]}.md").read_text()

    r = wiki_rebuild(home, "--yes")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    # refiled from nothing, in the sweep's order
    assert maintainer_ids(home) == SWEEP_ORDER, maintainer_ids(home)
    for vid in SWEEP_ORDER:
        assert (wiki / "sources" / f"{vid}.md").is_file(), f"{vid} was not refiled"
    index = (wiki / "index.md").read_text()
    for vid in SWEEP_ORDER:
        assert f"sources/{vid}.md" in index, f"the rebuilt catalog is missing {vid}:\n{index}"

    # the reset was real: a page nothing would have written back is gone
    assert not hand.exists(), (
        "a hand-written note survived a reset that claims to have emptied notes/ — "
        "then the rebuild is not a rebuild, it is a second pass over the old wiki"
    )

    # and the two things it may not touch are untouched
    assert brief.read_text() == house_rules, (
        "the brief is the user's, and it is the reason the rebuilt wiki will be "
        "better than the one it replaced"
    )
    log = (wiki / "log.md").read_text()
    assert log.startswith(old_log), (
        "the chronology is append-only through a rebuild too, or the record of the "
        "wiki that was is gone with it"
    )
    assert [op for op, _ in log_entries(wiki)] == ["file"] * 4 + ["rebuild"] + ["file"] * 4, (
        f"the reset owes the chronology one entry of its own, before the refilings "
        f"it caused: {log_entries(wiki)}"
    )

    # the history: one reset commit, then one commit per refiled video
    history = subjects(wiki)
    reset_at = history.index("wiki rebuild: reset")
    assert [s.split()[-1] for s in history[:reset_at]] == list(reversed(SWEEP_ORDER)), (
        f"each refiling is its own commit, gated on its own: {history}"
    )
    assert all(s.startswith("wiki file") for s in history[:reset_at]), history
    assert "user edits" in history[reset_at + 1], (
        f"the user's pending work is committed before the reset, so the reset has "
        f"something safe to be undone back to: {history}"
    )

    # the old wiki is one `git show` away, which is what makes the reset survivable
    reset = commit_named(wiki, "wiki rebuild: reset")
    recovered = git(wiki, "show", f"{reset}~1:notes/mine.md")
    assert recovered.returncode == 0 and marker in recovered.stdout, (
        f"the hand-written note is unrecoverable from the wiki's own history: "
        f"{recovered.stdout!r} {recovered.stderr!r}"
    )
    assert git(wiki, "show", f"{reset}~1:sources/{SWEEP_ORDER[0]}.md").stdout == old_page

    # what the reset commit itself contains: an emptied wiki, brief and log intact
    at_reset = git(wiki, "ls-tree", "-r", "--name-only", reset).stdout.split()
    assert not [p for p in at_reset if p.startswith(("sources/", "notes/"))], (
        f"the reset commit still holds pages it claimed to remove: {at_reset}"
    )
    assert "CLAUDE.md" in at_reset and "log.md" in at_reset, at_reset
    assert git(wiki, "show", f"{reset}:index.md").stdout.strip() == "", (
        "the reset leaves an empty catalog for the refiling to fill"
    )
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_a_refiling_that_fails_does_not_stop_the_rebuild(home, monkeypatch):
    """A rebuild is a sweep and tolerates a bad filing exactly as `sync` does. The
    video that fails is left unfiled and named, and the cost of that is the reason
    the old wiki stays in the history: the user can read the page they lost while
    they work out why the gate refused the new one."""
    wiki = file_everything(home, monkeypatch)
    set_maintainer(home, links_to_nothing_for(BROKEN))

    r = wiki_rebuild(home, "--yes")
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert maintainer_ids(home) == SWEEP_ORDER, (
        f"the rebuild stopped at the video that failed: {maintainer_ids(home)}"
    )
    assert not (wiki / "sources" / f"{BROKEN}.md").exists(), (
        "the rejected refiling was rolled back, so its page is not there"
    )
    for vid in SWEEP_ORDER:
        if vid != BROKEN:
            assert (wiki / "sources" / f"{vid}.md").is_file(), f"{vid} was not refiled"

    assert BROKEN in r.stderr and "nonexistent-page" in r.stderr, r.stderr
    line = summary_line(r)
    assert re.search(r"\b3\b", line) and re.search(r"\b1\b", line), line
    assert not git(wiki, "status", "--porcelain").stdout.strip()

    reset = commit_named(wiki, "wiki rebuild: reset")
    lost = git(wiki, "show", f"{reset}~1:sources/{BROKEN}.md")
    assert lost.returncode == 0 and lost.stdout.strip(), (
        "the page the rebuild could not replace is not recoverable from history"
    )


# --- refusals ----------------------------------------------------------------


def test_a_rebuild_with_no_wiki_exits_2(home, monkeypatch):
    """`file` and `sync` bring a wiki into being; rebuild only replaces one. A
    rebuild that scaffolded on the way past would answer a question about
    destroying something by creating it."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_rebuild(home, "--yes")
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert str(home / "wiki") in r.stderr, (
        f"the message names the wiki it went looking for: {r.stderr!r}"
    )
    assert not (home / "wiki").exists(), "rebuild is not how a wiki comes into being"
    assert not (home / "maintainer-ran").exists()
    assert wiki_rebuild(home).returncode == 2, "there is nothing to preview either"


def test_yes_without_a_maintainer_configured_exits_2(home, monkeypatch):
    """The seam is checked before anything is destroyed. A rebuild that reset the
    wiki and then discovered it had no agent to refile it with would have turned a
    missing config line into an empty wiki."""
    wiki = file_everything(home, monkeypatch)
    (home / "config.toml").write_text("# no seam configured\n")
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_rebuild(home, "--yes")
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert "maintainer_command" in r.stderr, (
        f"the message names the key the user has to set: {r.stderr!r}"
    )
    assert snapshot(wiki) == before and subjects(wiki) == history, (
        "a rebuild that cannot refile must not reset"
    )
