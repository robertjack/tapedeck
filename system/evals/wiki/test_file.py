"""Durable evals: the `file <id>` operation (SPEC-wiki-002).

Boundary: `python -m wiki file <id>`; maintainer seam faked through config.toml,
ask faked through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

What the verb owes the user, apart from the wiki it produces: it costs nothing
when there is nothing to do, it refuses before spending an agent invocation when
its preconditions are unmet, and it never loses work the user did by hand between
filings. The last one is why the run commits what it finds before it starts —
a rollback can only be safe if there is a commit underneath it that already
holds the user's edits.

The id grammar and the archive page are other components' vocabulary (LESSON-0003):
a well-formed id names a video ingest holds, and the page comes from archive.
"""

import re
from pathlib import Path

from conftest import set_maintainer
from wikilib import (
    ENTRY,
    FAILS,
    FILED,
    MUST_NOT_RUN,
    NEXT,
    RECORDS_THE_SEAM,
    ask_calls,
    filed,
    git,
    set_ask,
    snapshot,
    stocked,
    subjects,
    wiki_file,
)

MALFORMED = "not-an-id"      # the grammar ingest publishes is 11 characters wide
ABSENT = "nosuchvid00"       # well-formed, and in no library


# --- an accepted operation --------------------------------------------------


def test_a_good_maintainers_wiki_is_accepted_and_committed(home, monkeypatch):
    wiki = filed(home, monkeypatch)

    page = wiki / "sources" / f"{FILED}.md"
    assert page.is_file(), "the sources page is the record that this video is filed"
    assert f"watch?v={FILED}" in page.read_text(), "and it cites the video it is about"

    index = (wiki / "index.md").read_text()
    for linked in (f"sources/{FILED}.md", "notes/regeneration.md"):
        assert linked in index, f"the catalog is missing {linked}:\n{index}"

    log = (wiki / "log.md").read_text()
    assert ENTRY.search(log), f"the chronology gained no well-formed entry:\n{log}"
    assert FILED in log

    assert subjects(wiki)[0].startswith("wiki file"), subjects(wiki)
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_the_maintainer_is_handed_the_wiki_the_video_and_the_task(home, monkeypatch):
    """The seam is the whole interface between tapedeck and the agent: where it
    runs, what it is working on, and what it has been asked to do."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_THE_SEAM)
    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    # the record exists at all only because TAPEDECK_HOME reached the maintainer
    cwd, seen_wiki, seen_id, seen_page, _, *task = (
        (home / "maintainer-log").read_text().splitlines()
    )
    wiki = home / "wiki"
    assert Path(cwd).resolve() == wiki.resolve(), (
        f"the maintainer works from inside the wiki, so its own paths are the "
        f"wiki's paths: {cwd!r}"
    )
    assert Path(seen_wiki.split("=", 1)[1]).resolve() == wiki.resolve()
    assert seen_id.split("=", 1)[1] == FILED

    archive_page = Path(seen_page.split("=", 1)[1])
    assert archive_page.is_absolute() and archive_page.is_file(), (
        f"the archive page is handed over as a path that can be read from anywhere: "
        f"{seen_page!r}"
    )
    assert archive_page.resolve() == (home / "archive" / f"{FILED}.md").resolve()
    assert "\n".join(task).strip(), "the maintainer is given a task, not an empty stdin"


def test_the_gate_asks_ask_whether_the_citations_hold(home, monkeypatch):
    """Citation reading is ask's vocabulary (LESSON-0003) — the gate submits page
    text to its published verb rather than parsing deep links a second time."""
    filed(home, monkeypatch)
    calls = ask_calls(home)

    assert calls, "the gate never invoked ask at all"
    assert all("verify" in argv for argv, _ in calls), (
        f"the gate reached ask by some other verb than the published one: {calls}"
    )
    carrying_the_page = [argv for argv, text in calls if f"watch?v={FILED}&t=95s" in text]
    assert carrying_the_page, (
        f"the page carrying the citation is the text ask is given:\n{calls}"
    )
    assert any("--require-citation" not in argv for argv in carrying_the_page), (
        "a wiki page is not an answer: a note that cites nothing is legal, so the "
        f"link-truth check asks only whether the links a page does carry are true: "
        f"{carrying_the_page}"
    )


# --- refusals that cost nothing ---------------------------------------------


def test_an_already_filed_video_is_skipped_without_running_the_maintainer(home, monkeypatch):
    """The sources page is the filed-state marker, so the second call is a no-op:
    the expensive part is never reached, and the exit code stays 0 because
    nothing is wrong."""
    wiki = filed(home, monkeypatch)
    before, history = snapshot(wiki), subjects(wiki)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"an already-filed video is not an error:\n{r.stderr}"
    assert not (home / "maintainer-ran").exists(), "the maintainer was invoked anyway"
    assert FILED in r.stderr, f"the skip is said out loud: {r.stderr!r}"
    assert snapshot(wiki) == before and subjects(wiki) == history


def test_a_malformed_id_exits_2(home, monkeypatch):
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_file(home, MALFORMED)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert not (home / "maintainer-ran").exists()


def test_an_id_the_library_does_not_hold_exits_2(home, monkeypatch):
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_file(home, ABSENT)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert ABSENT in r.stderr
    assert not (home / "maintainer-ran").exists()


def test_a_video_with_no_archive_page_exits_1_and_says_what_to_run(home, monkeypatch):
    """A known video whose page archive never rendered is a job that cannot be
    done yet, not a mistyped id — the maintainer reads the page, so there is
    nothing for it to read."""
    stocked(home, pages=(FILED,))
    set_ask(monkeypatch, home)
    set_maintainer(home, MUST_NOT_RUN)

    r = wiki_file(home, NEXT)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert NEXT in r.stderr
    assert re.search(r"\badd\b", r.stderr), (
        f"the way out is the verb that renders the page: {r.stderr!r}"
    )
    assert not (home / "maintainer-ran").exists()


# --- work in the wiki that was not this run's --------------------------------


def test_a_maintainer_that_fails_leaves_the_wiki_where_it_was(home, monkeypatch):
    """A half-written wiki is worse than an unwritten one: whatever the failing
    run had already put on disk goes with it."""
    wiki = filed(home, monkeypatch)
    before, history = snapshot(wiki), subjects(wiki)
    set_maintainer(home, FAILS)

    r = wiki_file(home, NEXT)
    assert r.returncode == 1, f"a maintainer that fails fails the operation:\n{r.stdout}"
    assert r.stderr.strip(), "the failure is reported"
    assert snapshot(wiki) == before
    assert subjects(wiki) == history


def test_pending_user_edits_are_committed_before_the_maintainer_runs(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    note = wiki / "notes" / "regeneration.md"
    mine = "Mine: the thread to pull is the sandbox, not the model.\n"
    note.write_text(note.read_text() + mine)

    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    history = subjects(wiki)
    assert history[0].startswith("wiki file"), history
    assert "user edits" in history[1], (
        f"the user's writing is a commit of its own, made first, so the run that "
        f"follows can be undone without it: {history}"
    )
    kept = git(wiki, "show", "HEAD~1:notes/regeneration.md").stdout
    assert mine in kept, f"the 'user edits' commit does not hold the user's edit:\n{kept}"


def test_a_rollback_cannot_destroy_the_users_pending_edits(home, monkeypatch):
    """The same commit, doing the job it exists for."""
    wiki = filed(home, monkeypatch)
    note = wiki / "notes" / "regeneration.md"
    mine = "Mine: written by hand between two filings.\n"
    note.write_text(note.read_text() + mine)
    set_maintainer(home, FAILS)

    r = wiki_file(home, NEXT)
    assert r.returncode == 1
    assert mine in note.read_text(), (
        "the reset went back past the commit the user's edits were captured in, "
        "and took hand-written work with it"
    )
    assert not (wiki / "notes" / "half.md").exists(), (
        "the failed maintainer's writing survived the rollback"
    )


def test_a_video_added_after_the_wiki_exists_is_filed_into_it(home, monkeypatch):
    """The wiki grows: a second filing joins the first rather than replacing it."""
    wiki = filed(home, monkeypatch)
    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    assert (wiki / "sources" / f"{FILED}.md").is_file(), "the first filing is still filed"
    assert (wiki / "sources" / f"{NEXT}.md").is_file()
    index = (wiki / "index.md").read_text()
    assert f"sources/{FILED}.md" in index and f"sources/{NEXT}.md" in index
    assert len(ENTRY.findall((wiki / "log.md").read_text())) == 2
