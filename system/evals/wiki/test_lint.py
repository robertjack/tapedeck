"""Durable evals: `wiki lint` (SPEC-wiki-004).

Boundary: `python -m wiki lint [--json]`; library and wiki resolved from
$TAPEDECK_HOME exactly as `file` resolves them. The maintainer seam is faked
through config.toml and ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py),
though lint's own promise is that it never reaches for either — it only reads.

lint is doctor's mold applied to the wiki (SPEC-cli-007): a fixed-order report,
every check always printed, pass/fail/info as the only statuses, and a process
that changes nothing no matter what it finds. Each failure-class eval here starts
from a wiki that `file` already built cleanly and breaks exactly one thing by
hand — a legitimate way to reach that state, since the user edits the wiki by
hand too (SPEC-wiki-001) — then asks for the same two things every time: the one
check that should have caught it reports `fail`, and the detail names the thing
that broke.
"""

import json
import re
import shutil

from conftest import run_component, set_maintainer
from wikilib import (
    ASK_REPORTS_A_FABRICATION,
    FILED,
    MUST_NOT_RUN,
    NEXT,
    ask_calls,
    filed,
    git,
    set_ask,
    snapshot,
    subjects,
)

# SPEC-wiki-004 pins the checks and their order.
CHECKS = ("wikilinks", "citations", "index", "log", "sources", "filed", "unfiled", "orphans")
FAILABLE = ("wikilinks", "citations", "index", "log", "sources", "filed")
INFO_ONLY = ("unfiled", "orphans")
STATUSES = {"pass", "fail", "info"}


def wiki_lint(home, *args):
    return run_component("wiki", ["lint", *args], home)


def lint(home, *args):
    """Run `wiki lint --json` and return (result, {check: row})."""
    r = wiki_lint(home, "--json", *args)
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        raise AssertionError(
            f"`wiki lint --json` did not emit JSON (exit {r.returncode}):\n"
            f"stdout={r.stdout!r}\nstderr={r.stderr!r}"
        ) from exc
    return r, {row["check"]: row for row in rows}


# --- a wiki with nothing wrong ------------------------------------------------


def test_a_clean_wiki_passes_every_failable_check_in_order_and_stays_read_only(
    home, monkeypatch
):
    """Nothing here is broken: the six checks that can fail all pass, in the
    pinned order, and lint never reaches for the maintainer or commits anything
    — it only read the wiki it was handed."""
    wiki = filed(home, monkeypatch)  # FILED is filed; NEXT sits eligible, unfiled
    set_maintainer(home, MUST_NOT_RUN)
    before_subjects, before_snapshot = subjects(wiki), snapshot(wiki)
    # lint reads the library to judge the wiki; it writes nowhere in the home
    outside = {
        str(p.relative_to(home)): p.read_bytes()
        for p in sorted(home.rglob("*"))
        if p.is_file() and wiki not in p.parents
    }

    r, rows = lint(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert list(rows) == list(CHECKS), (
        f"every check is reported, in the fixed order, whatever its status: {list(rows)}"
    )
    for check in FAILABLE:
        assert rows[check]["status"] == "pass", f"{check} should pass clean: {rows[check]!r}"
    for check in INFO_ONLY:
        assert rows[check]["status"] == "info", (
            f"{check} is info-only and never decides the exit code: {rows[check]!r}"
        )

    assert not (home / "maintainer-ran").exists(), (
        "lint diagnoses the wiki; it never runs the maintainer to do it"
    )
    assert subjects(wiki) == before_subjects, "a read-only pass committed something"
    assert snapshot(wiki) == before_snapshot, "a read-only pass wrote to the wiki"
    assert {
        str(p.relative_to(home)): p.read_bytes()
        for p in sorted(home.rglob("*"))
        if p.is_file() and wiki not in p.parents
    } == outside, "a read-only pass wrote outside the wiki"


def test_unfiled_and_orphans_report_info_without_failing_the_run(home, monkeypatch):
    """Something is left to do — a video not yet filed, a page nothing wikilinks
    to — and both are exactly the shape sync's job describes, not a reason to
    fail the run."""
    wiki = filed(home, monkeypatch)
    (wiki / "notes" / "loose.md").write_text("# Loose\n\nStanding alone.\n")
    index = wiki / "index.md"
    index.write_text(index.read_text() + "- [Loose](notes/loose.md)\n")

    r, rows = lint(home)
    assert r.returncode == 0, (
        f"info never decides the exit code, whatever it has to report:\n{r.stdout}\n{r.stderr}"
    )
    for check in FAILABLE:
        assert rows[check]["status"] != "fail", (
            f"{check} broke for a reason unrelated to what this wiki left undone: {rows[check]!r}"
        )

    assert rows["unfiled"]["status"] == "info"
    assert NEXT in rows["unfiled"]["detail"], (
        f"the eligible, unfiled video is named: {rows['unfiled']!r}"
    )
    assert rows["orphans"]["status"] == "info"
    assert "loose" in rows["orphans"]["detail"].lower(), (
        f"the page nothing wikilinks to is named: {rows['orphans']!r}"
    )


def test_json_reports_the_same_checks_in_the_pinned_order(home, monkeypatch):
    filed(home, monkeypatch)
    r = wiki_lint(home, "--json")
    rows = json.loads(r.stdout)

    assert isinstance(rows, list) and rows, "--json emits a list of checks"
    assert [row["check"] for row in rows] == list(CHECKS)
    for row in rows:
        assert set(row) == {"check", "status", "detail"}, f"unexpected keys in {row!r}"
        assert row["status"] in STATUSES, f"{row['check']}: bad status {row['status']!r}"
        assert isinstance(row["detail"], str) and row["detail"].strip(), (
            f"{row['check']} carries no reason"
        )
    assert "\x1b" not in r.stdout


def test_the_human_report_prints_one_aligned_line_per_check(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    page = wiki / "sources" / f"{FILED}.md"
    page.write_text(page.read_text() + "\nSee also [[nonexistent-page]].\n")

    r = wiki_lint(home)
    assert r.returncode == 1
    assert "\x1b" not in r.stdout, "piped output carries no escape sequences (SPEC-cli-005)"

    _, rows = lint(home)
    columns = set()
    for name, row in rows.items():
        matches = [ln for ln in r.stdout.splitlines() if ln.strip().startswith(name)]
        assert len(matches) == 1, (
            f"expected exactly one report line opening with {name!r}, got {matches!r}"
        )
        line = matches[0]
        marker = re.search(rf"\b{row['status']}\b", line[line.index(name) + len(name):])
        assert marker, (
            f"the line for {name!r} does not carry its {row['status']!r} status: {line!r}"
        )
        columns.add(line.index(name) + len(name) + marker.start())
    assert len(columns) == 1, (
        f"the status begins at a different column on different lines: {sorted(columns)}"
    )


# --- read-only, and what that costs it -------------------------------------------


def test_lint_diagnoses_the_working_tree_and_leaves_it_pending(home, monkeypatch):
    """Two promises in one run. `file` commits pending hand-edits because it is
    about to risk work a rollback must not take with it; `lint` risks nothing, so
    a commit here would be a diagnosis quietly changing the thing it was asked to
    describe. What it reads is therefore the wiki on disk, uncommitted edits and
    all — the wiki the user is actually looking at."""
    wiki = filed(home, monkeypatch)
    history = subjects(wiki)
    page = wiki / "sources" / f"{FILED}.md"
    pending = "\nStill unsaved, and already broken: [[nonexistent-page]].\n"
    page.write_text(page.read_text() + pending)

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["wikilinks"]["status"] == "fail", (
        f"lint diagnosed the last commit rather than the wiki on disk: {rows['wikilinks']!r}"
    )
    assert subjects(wiki) == history, (
        "lint made a `user edits` commit; a read-only verb has nothing to protect"
    )
    assert pending in page.read_text(), "lint rewrote the page it was asked to read"
    assert git(wiki, "status", "--porcelain").stdout.strip(), (
        "the user's edit is still pending, exactly where they left it"
    )


def test_lint_needs_no_maintainer_seam(home, monkeypatch):
    """A wiki can be linted on a machine with no agent configured at all: the verb
    spends no maintainer invocation, so an unset seam is not its business — unlike
    `file` and `sync`, which exit 2 without one."""
    filed(home, monkeypatch)
    (home / "config.toml").write_text("# no seam configured\n")

    r, rows = lint(home)
    assert r.returncode == 0, (
        f"an unconfigured maintainer is not a broken wiki:\n{r.stdout}\n{r.stderr}"
    )
    assert list(rows) == list(CHECKS), list(rows)


def test_the_citations_check_reaches_ask_the_way_the_gate_does(home, monkeypatch):
    """Citation grammar is ask's vocabulary (LESSON-0003) and the linter reads it
    through the same published verb the acceptance gate uses. A linter that
    disagreed with the gate about a link would be worse than no linter: it would
    send the user to fix a page the gate is perfectly happy with."""
    filed(home, monkeypatch)
    (home / "ask-calls").unlink()  # the gate's calls; what follows is lint's own

    r, rows = lint(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert rows["citations"]["status"] == "pass"
    assert (home / "ask-calls").is_file(), "the citations check never invoked ask at all"

    calls = ask_calls(home)
    assert all("verify" in argv for argv, _ in calls), (
        f"lint reached ask by some other verb than the published one: {calls}"
    )
    assert all("--require-citation" not in argv for argv, _ in calls), (
        "a page that cites nothing has made no claim, so the check asks only whether "
        f"the links a page does carry are true: {calls}"
    )
    carrying_the_page = [text for _, text in calls if f"watch?v={FILED}&t=95s" in text]
    assert len(carrying_the_page) == 1, (
        f"one page's text per invocation, exactly as the gate submits it: {calls}"
    )


# --- one failure class per check -----------------------------------------------


def test_a_broken_wikilink_fails_the_wikilinks_check(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    page = wiki / "sources" / f"{FILED}.md"
    page.write_text(page.read_text() + "\nSee also [[nonexistent-page]].\n")

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["wikilinks"]["status"] == "fail"
    assert "nonexistent-page" in rows["wikilinks"]["detail"], (
        f"the unresolved target is named: {rows['wikilinks']!r}"
    )


def test_a_citation_ask_cannot_verify_fails_the_citations_check(home, monkeypatch):
    """ask's verdict is the check's verdict, and its words are the ones
    reported — the rules for reading a citation live in one place (LESSON-0003),
    the same seam the acceptance gate itself reads through."""
    filed(home, monkeypatch)
    set_ask(monkeypatch, home, ASK_REPORTS_A_FABRICATION)

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["citations"]["status"] == "fail"
    assert "unverifiable" in rows["citations"]["detail"], (
        f"what ask said about the link is what the user needs to see: {rows['citations']!r}"
    )


def test_a_page_missing_from_the_index_fails_the_index_check(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    index = wiki / "index.md"
    lines = [ln for ln in index.read_text().splitlines() if "notes/regeneration.md" not in ln]
    index.write_text("\n".join(lines) + "\n")

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["index"]["status"] == "fail"
    assert "regeneration" in rows["index"]["detail"].lower(), (
        f"the page missing from the catalog is named: {rows['index']!r}"
    )


def test_an_index_line_to_a_missing_page_fails_the_index_check(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    index = wiki / "index.md"
    index.write_text(index.read_text() + "- [Ghost](notes/ghost.md)\n")

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["index"]["status"] == "fail"
    assert "ghost" in rows["index"]["detail"].lower(), (
        f"the catalog entry with nothing behind it is named: {rows['index']!r}"
    )


def test_a_malformed_log_heading_fails_the_log_check(home, monkeypatch):
    wiki = filed(home, monkeypatch)
    log = wiki / "log.md"
    log.write_text(log.read_text() + "\n## [not-a-date] file missing-the-pipe\n")

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["log"]["status"] == "fail"
    assert "not-a-date" in rows["log"]["detail"], (
        f"the malformed heading is named: {rows['log']!r}"
    )


def test_a_source_page_with_no_self_citation_fails_the_sources_check(home, monkeypatch):
    """A page that cites a different video, or nothing at all, passes every
    other check in the gate — and still leaves the filed video unsourced."""
    wiki = filed(home, monkeypatch)
    page = wiki / "sources" / f"{FILED}.md"
    page.write_text(
        f"# {FILED}\n\nA note that never points back at the recording it is about. "
        "Belongs with [[regeneration|the idea behind it]].\n"
    )

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["sources"]["status"] == "fail"
    assert FILED in rows["sources"]["detail"], (
        f"the unsourced source page is named: {rows['sources']!r}"
    )


def test_a_source_pages_video_leaving_the_library_fails_the_filed_check(home, monkeypatch):
    """`rm` can leave knowledge dangling: the page still claims a video that is
    no longer here to check it against, and naming which video is the point."""
    filed(home, monkeypatch)
    shutil.rmtree(home / "library" / FILED)

    r, rows = lint(home)
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    assert rows["filed"]["status"] == "fail"
    assert FILED in rows["filed"]["detail"], (
        f"naming which video is missing is the point: {rows['filed']!r}"
    )


# --- the precondition -----------------------------------------------------------


def test_a_missing_wiki_exits_2_and_creates_nothing(home):
    """Unlike `file` and `sync`, lint never scaffolds: there is nothing to
    diagnose when there is no wiki, and it is not the verb that makes one."""
    r = wiki_lint(home)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert str(home / "wiki") in r.stderr, (
        f"the refusal names the path it looked for, because which wiki was resolved "
        f"is the whole question a surprising $TAPEDECK_HOME raises: {r.stderr!r}"
    )
    assert "invalid choice" not in r.stderr, (
        f"exit 2 here must mean 'no wiki to check', not 'lint is not a recognized "
        f"verb': {r.stderr!r}"
    )
    assert not r.stdout.strip(), "a usage failure has no report to print"
    assert not (home / "wiki").exists(), "lint must not create the wiki it was asked to check"
