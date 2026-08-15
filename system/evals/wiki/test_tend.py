"""Durable evals: `tend [--yes]` (SPEC-wiki-006).

Boundary: `python -m wiki tend`; the maintainer seam faked through config.toml,
ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py). tend reuses
`[wiki].maintainer_command` — the agent that writes the wiki is the agent that
tends it — so the fakes here are the same kind of shell script the filing suites
use, minus the video: a tend run is about the whole wiki and is handed no id.

`lint` asks the mechanical questions of a standing wiki (SPEC-wiki-004); tend
asks the ones only a reader can answer, which means putting a model in front of
the whole wiki and then not trusting a word of it. Two modes, and this suite is
about the guarantee each one makes.

Report mode makes the guarantee by force rather than by instruction: the agent is
asked to read and print, and afterwards tapedeck resets and cleans the tree
regardless of what it did, so a report run cannot change the wiki even when the
agent tries. That is why the meddling fake below matters more than the honest
one — an agent told to stay read-only and believed is not a guarantee, it is a
hope.

Apply mode makes it by reusing SPEC-wiki-002's gate whole, plus the one rule tend
needs and filing does not: source pages may not be deleted or renamed away. Their
existence is the filed-state marker (SPEC-wiki-001) and `sync`'s entire selection
rule, so a tend that tidied one away would silently un-file a video and the next
sweep would file it all over again. Notes are the opposite case and the evals
below hold both edges: reshaping, merging and deleting the prose layer is what
tending *is*, and a protection that reached into `notes/` would forbid the work.
"""

from pathlib import Path

from conftest import run_component, set_maintainer
from wikilib import (
    FILED,
    MUST_NOT_RUN,
    filed,
    git,
    log_entries,
    set_ask,
    snapshot,
    subjects,
)

# The second note the fixture wiki carries, written by the user's own hand: two
# notes are the least a wiki needs before "connect these" is a real finding.
SANDBOX = """# Sandbox

The thread worth pulling after the fixture show: what the sandbox does with a
file that appears while it is not looking.
"""

FINDINGS = "regeneration and sandbox circle the same idea and never link to each other"


def wiki_tend(home, *flags):
    return run_component("wiki", ["tend", *flags], home)


def tendable(home, monkeypatch):
    """A wiki worth tending: one filed video, the note the filing wrote, and a
    second note the user typed themselves — committed, so the working tree is
    clean and each eval below starts from history rather than from pending work.
    Returns the wiki directory."""
    wiki = filed(home, monkeypatch)
    (wiki / "notes" / "sandbox.md").write_text(SANDBOX)
    index = wiki / "index.md"
    index.write_text(index.read_text() + "- [Sandbox](notes/sandbox.md)\n")
    assert git(wiki, "add", "-A").returncode == 0
    r = git(
        wiki,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        "a note of my own",
    )
    assert r.returncode == 0, f"the fixture wiki must commit cleanly:\n{r.stderr}"
    return wiki


def rejected(home, monkeypatch, tender):
    """Run an apply-mode tend with a tender that breaks one rule, and hold it to
    the promise every rejection makes: exit 1, something on stderr to act on, and
    a wiki byte-identical to the commit it started from with no commit of its
    own. Returns the run so the caller can read the violation."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, tender)
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_tend(home, "--yes")
    assert r.returncode == 1, f"the tended wiki must not be accepted:\n{r.stdout}\n{r.stderr}"
    assert r.stderr.strip(), "a rejection that says nothing cannot be acted on"
    assert snapshot(wiki) == before, "a rejected tend leaves nothing behind"
    assert subjects(wiki) == history, "a rejected tend records no commit"
    return r


# --- the fakes ---------------------------------------------------------------
#
# Assembled from an honest body plus a single line that breaks one rule, so each
# eval names the one thing it changed (wikilib's arrangement, applied to a verb
# whose honest body is a rewrite of the prose layer rather than a filing).

READS_THE_TASK = """#!/bin/sh
cat > "$TAPEDECK_HOME/tend-task"
"""

REPORTS = (
    READS_THE_TASK
    + f"""
cat <<'REPORT'
{FINDINGS}
Nothing points at the sandbox note; it is a page the wiki mentions to no one.
REPORT
"""
)

RECORDS_THE_SEAM = """#!/bin/sh
{ pwd
  echo "home=$TAPEDECK_HOME"
  echo "wiki=$TAPEDECK_WIKI"
  echo "id=[$TAPEDECK_VIDEO_ID]"
  echo "--- task ---"
  cat
} > "$TAPEDECK_HOME/tender-log"
echo "nothing worth reporting today"
"""

# A reader that is not one: it prints its findings and then writes, edits, and
# deletes on its way out. Every one of these must be gone afterwards.
REPORTS_AND_MEDDLES = (
    REPORTS
    + f"""
echo "# Junk the reader invented" > notes/junk.md
echo "- also: the agent may rewrite this brief" >> CLAUDE.md
echo "A sentence nobody asked for." >> "sources/{FILED}.md"
rm notes/regeneration.md
"""
)

REPORTS_THEN_FAILS = (
    READS_THE_TASK
    + """
echo "half a finding before"
echo "the wiki was unreadable partway through" >&2
echo "# Half a thought" > notes/half.md
exit 3
"""
)

# The catalog, rebuilt from what is actually on disk — what a tender that has
# just reshaped the prose layer owes index.md.
CATALOGS = """
{ for page in sources/*.md notes/*.md; do
    [ -e "$page" ] || continue
    echo "- [$(basename "$page" .md)]($page)"
  done; } > index.md
"""

LOGS_THE_TEND = """
{ echo; echo "## [$(date +%Y-%m-%d)] tend | connected the two notes"; echo;
  echo "The notes had been circling each other; now they say so."; } >> log.md
"""

CROSS_LINKS = (
    READS_THE_TASK
    + """
{ echo; echo "The same ground from the other end: [[sandbox]]."; } >> notes/regeneration.md
{ echo; echo "Which is [[regeneration]] arrived at backwards."; } >> notes/sandbox.md
"""
    + CATALOGS
    + LOGS_THE_TEND
)

# Merging the prose layer down: a note the tender judged redundant, removed, with
# the catalog brought back into agreement. Nothing links to it, so nothing breaks.
PRUNES_A_NOTE = (
    READS_THE_TASK
    + """
rm notes/sandbox.md
"""
    + CATALOGS
    + LOGS_THE_TEND
)

# The same tidying instinct applied one directory over. The wikilink into the
# source page is rewritten away too, so the only rule left broken is the one
# about `sources/` itself.
DELETES_A_SOURCE_PAGE = (
    READS_THE_TASK
    + f"""
rm "sources/{FILED}.md"
cat > notes/regeneration.md <<'MD'
# Regeneration

The idea, with the recording it came from folded into the prose.
MD
"""
    + CATALOGS
    + LOGS_THE_TEND
)

RENAMES_A_SOURCE_PAGE_AWAY = (
    READS_THE_TASK
    + f"""
mv "sources/{FILED}.md" "notes/{FILED}.md"
"""
    + CATALOGS
    + LOGS_THE_TEND
)

LINKS_TO_NOTHING = (
    CROSS_LINKS
    + """
echo "Compare with [[nonexistent-page]]." >> notes/sandbox.md
"""
)

EDITS_THE_BRIEF = (
    CROSS_LINKS
    + """
echo "- also: tidy the sources tree while you are in there" >> CLAUDE.md
"""
)


# --- report mode -------------------------------------------------------------


def test_the_report_reaches_the_user_and_the_wiki_is_untouched(home, monkeypatch):
    """The default mode is a reading, and a reading's whole product is prose. It
    lands on stdout, where the user asked for it — and the wiki afterwards is the
    wiki from before, byte for byte, with no commit to show that anything ran."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, REPORTS)
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_tend(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert FINDINGS in r.stdout, (
        f"what the agent found is what the user came for, relayed rather than "
        f"summarized: {r.stdout!r}"
    )
    assert snapshot(wiki) == before, "a report changed the wiki it was reporting on"
    assert subjects(wiki) == history, "a report is not an event in the wiki's history"
    assert not git(wiki, "status", "--porcelain").stdout.strip()
    assert "tend" not in "\n".join(op for op, _ in log_entries(wiki)), (
        "a report wrote itself into the chronology, which records what the wiki "
        "became and not what was said about it"
    )


def test_a_report_run_cannot_change_the_wiki_even_when_the_agent_tries(home, monkeypatch):
    """The guarantee is mechanical, not contractual. This agent prints its
    findings and then writes a page, edits the brief, edits a source page and
    deletes a note — and the reset and clean that follow every report run leave
    no trace of any of it. An agent that was asked to stay read-only and simply
    believed would fail here, which is the point of asking."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, REPORTS_AND_MEDDLES)
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_tend(home)
    assert r.returncode == 0, f"the report itself succeeded:\n{r.stdout}\n{r.stderr}"
    assert FINDINGS in r.stdout

    assert snapshot(wiki) == before, (
        "the tree the meddling reader left behind is not the tree it was handed: "
        "reset --hard alone leaves untracked pages standing, and clean -fd alone "
        "leaves edits to tracked ones"
    )
    assert not (wiki / "notes" / "junk.md").exists()
    assert (wiki / "notes" / "regeneration.md").is_file(), "the deleted note came back"
    assert subjects(wiki) == history
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_a_tender_that_fails_in_report_mode_exits_1(home, monkeypatch):
    """A crashed agent has not read the wiki, whatever it managed to print on the
    way down, and the run says so. The tree is still restored — the discard is
    unconditional or it is not a guarantee."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, REPORTS_THEN_FAILS)
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_tend(home)
    assert r.returncode == 1, f"a tender that fails fails the run:\n{r.stdout}\n{r.stderr}"
    assert r.stderr.strip(), "the failure is reported"
    assert snapshot(wiki) == before, (
        "the half-written page the failing reader left is still there"
    )
    assert subjects(wiki) == history


def test_the_tender_is_handed_the_wiki_and_a_task(home, monkeypatch):
    """The seam is the whole interface: where the agent runs, which wiki it is
    about, and what it has been asked to do. There is no video id in it — tend is
    a verb about the wiki entire."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, RECORDS_THE_SEAM)

    r = wiki_tend(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    # the record exists at all only because TAPEDECK_HOME reached the tender
    cwd, seen_home, seen_wiki, seen_id, _, *task = (
        (home / "tender-log").read_text().splitlines()
    )
    assert Path(cwd).resolve() == wiki.resolve(), (
        f"the tender reads from inside the wiki, so its own paths are the wiki's "
        f"paths: {cwd!r}"
    )
    assert Path(seen_home.split("=", 1)[1]).resolve() == home.resolve()
    assert Path(seen_wiki.split("=", 1)[1]).resolve() == wiki.resolve()
    assert seen_id == "id=[]", (
        f"no video id is set for a tend: the run is about no one video, and a "
        f"variable naming one would lie about its scope: {seen_id!r}"
    )
    assert "\n".join(task).strip(), "the tender is given a task, not an empty stdin"


# --- apply mode --------------------------------------------------------------


def test_an_accepted_tend_is_committed_and_logged(home, monkeypatch):
    """The work tending exists to do: two pages that were about the same thing
    now say so, and the catalog agrees. It lands the way every accepted wiki
    operation lands — one commit, one chronology entry, a clean tree."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, CROSS_LINKS)
    old_log = (wiki / "log.md").read_text()

    r = wiki_tend(home, "--yes")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    assert "[[sandbox]]" in (wiki / "notes" / "regeneration.md").read_text()
    assert "[[regeneration]]" in (wiki / "notes" / "sandbox.md").read_text()

    assert subjects(wiki)[0] == "wiki tend", subjects(wiki)
    assert not git(wiki, "status", "--porcelain").stdout.strip()

    log = (wiki / "log.md").read_text()
    assert log.startswith(old_log), (
        "the chronology is append-only through a tend as well, or an agent editing "
        "the whole wiki can edit the record of what it did to it"
    )
    assert log_entries(wiki)[-1][0] == "tend", (
        f"the operation owes the chronology an entry of its own, named for the verb "
        f"that made it: {log_entries(wiki)}"
    )


def test_a_tend_may_delete_a_note_it_judged_redundant(home, monkeypatch):
    """Reshaping the prose layer is the work, so the protection one directory
    over must not reach into this one. A note removed with the catalog brought
    into agreement is an accepted tend, not a violation."""
    wiki = tendable(home, monkeypatch)
    set_maintainer(home, PRUNES_A_NOTE)

    r = wiki_tend(home, "--yes")
    assert r.returncode == 0, (
        f"deleting a note is what tending a wiki looks like:\n{r.stdout}\n{r.stderr}"
    )
    assert not (wiki / "notes" / "sandbox.md").exists(), "the note survived the tend"
    assert "notes/sandbox.md" not in (wiki / "index.md").read_text(), (
        "the catalog still promises a page the tend removed"
    )
    assert (wiki / "sources" / f"{FILED}.md").is_file()
    assert subjects(wiki)[0] == "wiki tend", subjects(wiki)


def test_pending_user_edits_are_committed_before_the_tender_runs(home, monkeypatch):
    """The same commit `file` makes, for the same reason: a tend can be rolled
    back, and the hand-written line sitting in the working tree when it started
    must be on the far side of that rollback rather than inside it."""
    wiki = tendable(home, monkeypatch)
    note = wiki / "notes" / "sandbox.md"
    mine = "Mine: the thread to pull is the sandbox, not the model.\n"
    note.write_text(note.read_text() + mine)
    set_maintainer(home, CROSS_LINKS)

    r = wiki_tend(home, "--yes")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    history = subjects(wiki)
    assert history[0] == "wiki tend", history
    assert "user edits" in history[1], (
        f"the user's writing is a commit of its own, made first, so the tend that "
        f"follows can be undone without it: {history}"
    )
    kept = git(wiki, "show", "HEAD~1:notes/sandbox.md").stdout
    assert mine in kept, f"the 'user edits' commit does not hold the user's edit:\n{kept}"
    assert mine in note.read_text(), "and the tend wrote over it on the way past"


# --- what the gate refuses ---------------------------------------------------


def test_a_tend_that_deletes_a_source_page_is_rejected(home, monkeypatch):
    """The rule tend needs and filing does not. A source page's existence is the
    filed-state marker (SPEC-wiki-001) and the whole of `sync`'s selection rule,
    so a tender that folded one into a note would un-file that video without
    saying so, and the next sweep would spend a maintainer run refiling it."""
    r = rejected(home, monkeypatch, DELETES_A_SOURCE_PAGE)
    assert FILED in r.stderr, (
        f"the violation names the source page that went missing, or the user has "
        f"to diff the wiki against its own history to find out: {r.stderr!r}"
    )
    assert "sources" in r.stderr, r.stderr


def test_a_tend_that_renames_a_source_page_away_is_rejected(home, monkeypatch):
    """Moved out of `sources/` is deleted as far as the filed-state marker is
    concerned: the page still exists, the video is unfiled, and nothing in the
    wiki reads as though anything happened."""
    r = rejected(home, monkeypatch, RENAMES_A_SOURCE_PAGE_AWAY)
    assert FILED in r.stderr, r.stderr


def test_a_tend_that_breaks_a_wikilink_is_rejected(home, monkeypatch):
    """SPEC-wiki-002's gate, whole and unmodified: an agent rewriting the prose
    layer is exactly the agent most likely to leave a link pointing at a page it
    just renamed, and the rejection names the target that dead-ends."""
    r = rejected(home, monkeypatch, LINKS_TO_NOTHING)
    assert "nonexistent-page" in r.stderr, (
        f"the unresolved target is named: {r.stderr!r}"
    )


def test_a_tend_that_edits_the_brief_is_rejected(home, monkeypatch):
    """The brief is the user's half of the arrangement, and a tender reading the
    whole wiki reads the brief with it. It may not answer back."""
    r = rejected(home, monkeypatch, EDITS_THE_BRIEF)
    assert "CLAUDE.md" in r.stderr, r.stderr


# --- refusals that cost nothing ----------------------------------------------


def test_a_missing_maintainer_command_exits_2_naming_the_key(home, monkeypatch):
    """tend has no seam of its own: the agent that writes the wiki is the agent
    that tends it. When that line is not in config.toml there is nothing to run,
    in either mode, and the message says which key to set."""
    wiki = tendable(home, monkeypatch)
    (home / "config.toml").write_text("# no seam configured\n")
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_tend(home)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert "maintainer_command" in r.stderr, (
        f"the message names the key the user has to set: {r.stderr!r}"
    )
    assert "invalid choice" not in r.stderr, (
        f"exit 2 here must mean 'no agent is configured', not 'tend is not a "
        f"recognized verb': {r.stderr!r}"
    )
    assert snapshot(wiki) == before and subjects(wiki) == history


def test_a_missing_wiki_exits_2_naming_the_path(home, monkeypatch):
    """`file` and `sync` scaffold because they are about to write a filing into
    the wiki; tend has nothing to say about a wiki that does not exist yet, and
    lint's rule applies — name the path that was resolved, since a surprising
    $TAPEDECK_HOME is the whole question."""
    set_ask(monkeypatch, home)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_tend(home)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert str(home / "wiki") in r.stderr, (
        f"the refusal names the wiki it went looking for: {r.stderr!r}"
    )
    assert "invalid choice" not in r.stderr, (
        f"exit 2 here must mean 'there is no wiki to tend', not 'tend is not a "
        f"recognized verb': {r.stderr!r}"
    )
    assert not (home / "wiki").exists(), "tend is not how a wiki comes into being"
    assert not (home / "maintainer-ran").exists(), "the agent was invoked anyway"
    assert wiki_tend(home, "--yes").returncode == 2, "and --yes is no more of an invitation"
