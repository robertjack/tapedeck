"""Ephemeral unit tests for wiki — disposable, unlike system/evals/wiki.

These poke at the pieces the durable evals only ever see through the process
boundary: how a page is read, what each acceptance check decides on its own, and
that the git lifecycle really does put a wiki back where it was. The maintainer
never runs here — the fakes in the durable suite cover that — so what is under
test is the deterministic edge, which is the only part this component owns.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from wiki import Failure, Usage, gate, layout, lint, seams
from wiki.layout import BRIEF, INDEX, LOG, NOTES, SOURCES
from wiki.repo import DEFAULT_BRIEF, SCAFFOLD, USER_EDITS, Repo

VID = "dQw4w9WgXcQ"
OTHER = "plainvide00"
LINK = "https://www.youtube.com/watch?v={id}&t=95s"


# --- fixtures: a wiki on disk, and a library beside it ---


def make_wiki(tmp_path, pages=None, index=None, log=None, brief=DEFAULT_BRIEF):
    """A wiki directory with whatever pages a test needs. No git, no library:
    every check in gate.py reads the working tree and nothing else."""
    wiki = tmp_path / "wiki"
    (wiki / SOURCES).mkdir(parents=True)
    (wiki / NOTES).mkdir(parents=True)
    (wiki / BRIEF).write_text(brief)
    (wiki / LOG).write_text(log if log is not None else "")
    for name, text in (pages or {}).items():
        path = wiki / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if index is None:
        index = "".join(f"- [{name}]({name})\n" for name in (pages or {}))
    (wiki / INDEX).write_text(index)
    return wiki


def filed_wiki(tmp_path, **kwargs):
    """The shape a clean filing leaves: a source page citing its own video and a
    note the two link to each other through."""
    pages = {
        f"{SOURCES}/{VID}.md": f"# {VID}\n\nFiled from [it]({LINK.format(id=VID)}).\n"
        "Belongs with [[regeneration|the idea]].\n",
        f"{NOTES}/regeneration.md": f"# Regeneration\n\nTraced to [[{VID}]].\n",
    }
    return make_wiki(tmp_path, pages, log=f"## [2026-08-14] file | {VID}\n\nFiled.\n", **kwargs)


def stock(home, video_id=VID, upload_date="2026-01-15", media=True, page=True):
    entry = home / "library" / video_id
    entry.mkdir(parents=True)
    if media:
        (entry / "video.mp4").write_bytes(b"\x00")
    (entry / "meta.json").write_text(
        json.dumps({"id": video_id, "title": "T", "channel": "C", "upload_date": upload_date})
    )
    if page:
        (home / "archive").mkdir(exist_ok=True)
        (home / "archive" / f"{video_id}.md").write_text("# page\n")
    return entry


# --- reading a page (contracts/wiki-layout.md) ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("[[plain]]", ["plain"]),
        ("[[target|alias]]", ["target"]),
        ("[[ spaced ]]", ["spaced"]),
        ("[[a]] and [[b|c]]", ["a", "b"]),
        ("no links here", []),
        ("[single] is not one", []),
    ],
)
def test_the_target_is_the_text_before_the_first_pipe(text, expected):
    assert layout.targets(text) == expected


def test_wikilink_targets_keep_their_case():
    """`[[Regeneration]]` beside `regeneration.md` works in one reader and dangles
    in another, so the strict reading is the only one that travels."""
    assert layout.targets("[[Regeneration]]") == ["Regeneration"]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("- [Note](notes/a.md)", ["notes/a.md"]),
        ("- [Note](./notes/a.md)", ["notes/a.md"]),
        ("- [Note](notes/a.md#heading)", ["notes/a.md"]),
        ("- [Home](https://example.com/a.md)", []),
        ("- [Anchor](#section)", []),
        ("plain text", []),
    ],
)
def test_the_catalog_reads_local_page_links_only(line, expected):
    assert layout.catalogued(line) == expected


@pytest.mark.parametrize(
    "text, video_id, cited",
    [
        (LINK.format(id=VID), VID, True),
        (f"[x]({LINK.format(id=VID)}).", VID, True),
        (LINK.format(id=OTHER), VID, False),
        (f"the video {VID} was good", VID, False),  # a mention is not a citation
        (f"https://www.youtube.com/watch?v={VID}", VID, False),  # no moment claimed
    ],
)
def test_a_page_cites_a_video_only_by_deep_linking_a_moment_in_it(text, video_id, cited):
    assert layout.cites(text, video_id) is cited


def test_the_chronology_is_only_ever_appended_to(tmp_path):
    log = tmp_path / LOG
    log.write_text("## [2026-08-01] file | earlier\n\nWas here first.\n")
    before = log.read_bytes()

    layout.append_entry(log, "rebuild", "everything", "And then this.")

    assert log.read_bytes().startswith(before), "the entry before this one was disturbed"
    assert layout.ENTRY.search(log.read_text().split("Was here first.")[1])


def test_an_entry_appended_to_an_empty_log_starts_the_file(tmp_path):
    log = tmp_path / LOG
    log.write_text("")
    layout.append_entry(log, "file", VID, "First.")
    assert log.read_text().startswith("## [")


# --- what a sweep may file (SPEC-wiki-003) ---


def test_eligibility_is_a_well_formed_id_present_media_and_a_rendered_page(tmp_path):
    home = tmp_path
    stock(home, "oldest00001", "2019-03-04")
    stock(home, "medialess01", "2020-01-01", media=False)
    stock(home, "unrendered1", "2020-01-01", page=False)
    (home / "library" / "reading-notes").mkdir()

    notes = []
    ready, skipped = layout.eligible(home, notes.append)

    assert ready == ["oldest00001"]
    assert skipped == 3
    for name in ("medialess01", "unrendered1", "reading-notes"):
        assert any(name in note for note in notes), f"{name} was skipped silently"


def test_the_sweep_order_is_upload_date_ascending_with_ties_broken_by_id(tmp_path):
    home = tmp_path
    for video_id, when in (
        ("tie-zebra-2", "2023-05-05"),
        ("middle00002", "2021-07-09"),
        ("tie-alpha-1", "2023-05-05"),
        ("oldest00001", "2019-03-04"),
    ):
        stock(home, video_id, when)

    ready, _ = layout.eligible(home)
    assert ready == ["oldest00001", "middle00002", "tie-alpha-1", "tie-zebra-2"]


def test_a_video_whose_metadata_cannot_be_read_files_last_rather_than_never(tmp_path):
    """The archive page is what a filing reads, so illegible metadata is no
    reason to leave a video out of the wiki forever — it only loses its place."""
    home = tmp_path
    stock(home, "readable001", "2030-01-01")
    entry = stock(home, "unreadable1", "2019-01-01")
    (entry / "meta.json").write_text("{not json")

    ready, skipped = layout.eligible(home)
    assert ready == ["readable001", "unreadable1"]
    assert skipped == 0


# --- the checks, one failure class at a time (SPEC-wiki-002) ---


def test_a_clean_wiki_trips_none_of_the_standing_checks(tmp_path):
    wiki = filed_wiki(tmp_path)
    assert gate.unresolved(wiki) == []
    assert gate.uncatalogued(wiki) == []
    assert gate.dangling(wiki) == []
    assert gate.unsourced(wiki) == []
    assert gate.malformed(wiki) == []
    assert gate.orphans(wiki) == []


def test_a_dangling_wikilink_names_the_page_and_the_target(tmp_path):
    wiki = filed_wiki(tmp_path)
    page = wiki / SOURCES / f"{VID}.md"
    page.write_text(page.read_text() + "\nCompare with [[nonexistent-page]].\n")

    assert gate.unresolved(wiki) == [(f"{SOURCES}/{VID}.md", "nonexistent-page")]


def test_a_wikilink_resolves_to_a_page_at_any_depth(tmp_path):
    wiki = make_wiki(
        tmp_path,
        {f"{NOTES}/deep/nested/idea.md": "# Idea\n", f"{NOTES}/a.md": "See [[idea]].\n"},
    )
    assert gate.unresolved(wiki) == []


def test_the_catalog_is_checked_in_both_directions(tmp_path):
    wiki = filed_wiki(tmp_path)
    (wiki / NOTES / "stray.md").write_text("# Stray\n")
    index = wiki / INDEX
    index.write_text(index.read_text() + f"- [Ghost]({NOTES}/ghost.md)\n")

    assert gate.uncatalogued(wiki) == [f"{NOTES}/stray.md"]
    assert gate.dangling(wiki) == [f"{NOTES}/ghost.md"]


def test_the_three_pinned_files_are_never_owed_a_catalog_line(tmp_path):
    wiki = filed_wiki(tmp_path, index="")
    assert set(gate.uncatalogued(wiki)) == {f"{SOURCES}/{VID}.md", f"{NOTES}/regeneration.md"}


def test_a_source_page_that_cites_only_another_video_is_unsourced(tmp_path):
    wiki = filed_wiki(tmp_path)
    page = wiki / SOURCES / f"{VID}.md"
    page.write_text(f"# {VID}\n\nSame ground as [other]({LINK.format(id=OTHER)}).\n")

    assert gate.unsourced(wiki) == [VID]


def test_a_heading_that_opens_like_an_entry_and_is_not_one_is_named(tmp_path):
    wiki = filed_wiki(tmp_path)
    log = wiki / LOG
    log.write_text(log.read_text() + "\n## [not-a-date] file missing-the-pipe\n")

    assert gate.malformed(wiki) == ["## [not-a-date] file missing-the-pipe"]
    assert gate.malformed(filed_wiki(tmp_path / "clean")) == []


def test_the_catalog_does_not_count_as_an_incoming_link(tmp_path):
    """index.md links every page by rule, so counting it would mean no page is
    ever an orphan and the finding would never say anything."""
    wiki = filed_wiki(tmp_path)
    (wiki / NOTES / "loose.md").write_text("# Loose\n\nStanding alone.\n")
    index = wiki / INDEX
    index.write_text(index.read_text() + f"- [Loose]({NOTES}/loose.md)\n")

    assert gate.orphans(wiki) == [f"{NOTES}/loose.md"]


# --- the gate as a whole ---


def all_links_hold(monkeypatch):
    monkeypatch.setattr(seams, "verify", lambda home, text: None)


def test_the_gate_reports_every_violation_rather_than_the_first(tmp_path, monkeypatch):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    page = wiki / SOURCES / f"{VID}.md"
    page.write_text(page.read_text() + "\nCompare with [[nonexistent-page]].\n")
    (wiki / NOTES / "stray.md").write_text("# Stray\n")

    problems = gate.violations(tmp_path, wiki, VID, (wiki / BRIEF).read_bytes(), b"")

    assert any("nonexistent-page" in problem for problem in problems)
    assert any("stray" in problem for problem in problems)


def test_any_change_at_all_to_the_brief_fails_the_operation(tmp_path, monkeypatch):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    before = (wiki / BRIEF).read_bytes()
    (wiki / BRIEF).write_text(DEFAULT_BRIEF + "- also: rename pages freely\n")

    problems = gate.violations(tmp_path, wiki, VID, before, b"")
    assert [problem for problem in problems if BRIEF in problem], problems


def test_the_gate_relays_what_ask_said_about_a_link(tmp_path, monkeypatch):
    """ask's verdict is the gate's verdict and its words are the ones reported:
    the rules for reading a citation live in one place (LESSON-0003)."""
    monkeypatch.setattr(seams, "verify", lambda home, text: "unverifiable citation: t=9999s")
    wiki = filed_wiki(tmp_path)

    problems = gate.violations(tmp_path, wiki, VID, (wiki / BRIEF).read_bytes(), b"")
    assert any("unverifiable citation: t=9999s" in problem for problem in problems)


@pytest.mark.parametrize(
    "log_now, before",
    [
        # rewritten from the top, which is what "keep the log neat" produces
        ("# tidied\n\n## [2026-08-14] file | x\n\nb\n", b"## [2026-08-01] file | old\n"),
        # preserved, but the operation recorded nothing of the pinned shape
        ("## [2026-08-01] file | old\nnothing well formed added\n", b"## [2026-08-01] file | old\n"),
        # nothing at all
        ("", b""),
    ],
)
def test_the_chronology_must_grow_at_the_end_and_only_there(
    tmp_path, monkeypatch, log_now, before
):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    (wiki / LOG).write_text(log_now)

    problems = gate.violations(tmp_path, wiki, VID, (wiki / BRIEF).read_bytes(), before)
    assert [problem for problem in problems if LOG in problem], problems


def test_the_gate_is_silent_on_a_wiki_that_holds_together(tmp_path, monkeypatch):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    assert gate.violations(tmp_path, wiki, VID, (wiki / BRIEF).read_bytes(), b"") == []


# --- the repository (SPEC-wiki-001) ---


def git(wiki, *args):
    return subprocess.run(["git", *args], cwd=wiki, capture_output=True, text=True)


def subjects(wiki):
    return git(wiki, "log", "--format=%s").stdout.splitlines()


def test_the_scaffold_is_one_commit_of_exactly_the_pinned_tree(tmp_path):
    repo = Repo(tmp_path / "wiki")
    repo.ensure()

    wiki = repo.path
    assert (wiki / SOURCES).is_dir() and (wiki / NOTES).is_dir()
    assert (wiki / BRIEF).read_text() == DEFAULT_BRIEF
    assert (wiki / INDEX).read_text() == "" and (wiki / LOG).read_text() == ""
    assert subjects(wiki) == [SCAFFOLD]
    assert git(wiki, "rev-parse", "--show-toplevel").stdout.strip().endswith("wiki")
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_scaffolding_happens_once_and_never_again(tmp_path):
    repo = Repo(tmp_path / "wiki")
    repo.ensure()
    mine = "# House rules\n\nOne page per idea.\n"
    (repo.path / BRIEF).write_text(mine)
    repo.commit("mine")

    repo.ensure()
    assert (repo.path / BRIEF).read_text() == mine, "a second call rewrote the brief"
    assert subjects(repo.path) == ["mine", SCAFFOLD]


def test_a_rollback_removes_untracked_work_and_keeps_the_users_commit(tmp_path):
    """A reset alone leaves exactly the half-written pages the rollback exists to
    remove, and stopping one commit short would take the user's writing with it."""
    repo = Repo(tmp_path / "wiki")
    repo.ensure()
    wiki = repo.path
    mine = "Mine: written by hand between two filings.\n"
    (wiki / NOTES / "mine.md").write_text(mine)

    repo.commit_pending()
    before = repo.head()
    (wiki / NOTES / "half.md").write_text("half a thought\n")
    (wiki / INDEX).write_text("- [Half](notes/half.md)\n")
    repo.restore(before)

    assert (wiki / NOTES / "mine.md").read_text() == mine
    assert not (wiki / NOTES / "half.md").exists(), "an untracked page survived the rollback"
    assert (wiki / INDEX).read_text() == ""
    assert subjects(wiki) == [USER_EDITS, SCAFFOLD]


def test_a_rollback_puts_the_wikis_shape_back(tmp_path):
    """git is indifferent to empty directories and a clean takes them with it,
    which is not a licence to leave the wiki without sources/ and notes/."""
    repo = Repo(tmp_path / "wiki")
    repo.ensure()
    repo.restore(repo.head())
    assert (repo.path / SOURCES).is_dir() and (repo.path / NOTES).is_dir()


def test_nothing_pending_means_no_commit_of_its_own(tmp_path):
    repo = Repo(tmp_path / "wiki")
    repo.ensure()
    repo.commit_pending()
    assert subjects(repo.path) == [SCAFFOLD]


def test_the_scaffolded_brief_survives_the_gate_it_describes(tmp_path, monkeypatch):
    """The default brief is read by the same checks as every other page, so an
    example wikilink or a specimen URL in it would fail every filing."""
    all_links_hold(monkeypatch)
    repo = Repo(tmp_path / "wiki")
    repo.ensure()
    assert gate.unresolved(repo.path) == []
    assert "youtube.com" not in DEFAULT_BRIEF, "a specimen URL is checked as a claim"


# --- the seam (SPEC-core-004) ---


def test_a_missing_maintainer_seam_names_the_key_and_the_file(tmp_path):
    (tmp_path / "config.toml").write_text("# no seam configured\n")
    with pytest.raises(Usage) as raised:
        seams.maintainer_command(tmp_path)
    assert seams.MAINTAINER_KEY in str(raised.value)
    assert str(tmp_path / "config.toml") in str(raised.value)


@pytest.mark.parametrize("body", ['[wiki]\nmaintainer_command = ""\n', "", "[wiki]\n"])
def test_an_empty_or_absent_seam_is_a_usage_error(tmp_path, body):
    (tmp_path / "config.toml").write_text(body)
    with pytest.raises(Usage):
        seams.maintainer_command(tmp_path)


def test_a_configured_seam_comes_back_stripped(tmp_path):
    (tmp_path / "config.toml").write_text('[wiki]\nmaintainer_command = "  sh run.sh  "\n')
    assert seams.maintainer_command(tmp_path) == "sh run.sh"


def test_config_that_is_not_toml_is_a_usage_error_not_a_crash(tmp_path):
    (tmp_path / "config.toml").write_text("[wiki\n")
    with pytest.raises(Usage):
        seams.maintainer_command(tmp_path)


def test_the_task_tells_the_maintainer_what_it_is_filing(tmp_path):
    task = seams.task(VID, tmp_path / "archive" / f"{VID}.md", "2026-08-14")
    assert VID in task and str(tmp_path) in task
    assert f"## [2026-08-14] file | {VID}" in task, "the log's shape is spelled out"


def test_ask_is_reached_by_the_documented_override(monkeypatch):
    monkeypatch.delenv(seams.ASK_ENV, raising=False)
    assert seams.ask_argv()[1:] == ["-m", "ask"]
    monkeypatch.setenv(seams.ASK_ENV, "sh /tmp/fake ask.sh")
    assert seams.ask_argv() == ["sh", "/tmp/fake", "ask.sh"]


def test_verify_relays_what_ask_wrote_and_says_nothing_of_its_own(tmp_path, monkeypatch):
    script = tmp_path / "ask.sh"
    script.write_text('#!/bin/sh\ncat > /dev/null\necho "unverifiable: t=9999s" >&2\nexit 1\n')
    monkeypatch.setenv(seams.ASK_ENV, f"sh {script}")
    assert seams.verify(tmp_path, "text") == "unverifiable: t=9999s"

    script.write_text("#!/bin/sh\ncat > /dev/null\n")
    assert seams.verify(tmp_path, "text") is None


def test_ask_that_cannot_be_reached_is_an_operation_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(seams.ASK_ENV, str(tmp_path / "not-a-program"))
    with pytest.raises(Failure):
        seams.verify(tmp_path, "text")


# --- the report (SPEC-wiki-004) ---


def test_every_check_is_reported_in_the_pinned_order(tmp_path, monkeypatch):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    stock(tmp_path, VID)

    rows = lint.diagnose(tmp_path, wiki)
    assert [row["check"] for row in rows] == list(lint.CHECKS)
    assert all(row["detail"].strip() for row in rows), "a check with no reason given"
    assert {row["status"] for row in rows} <= {lint.PASS, lint.FAIL, lint.INFO}


def test_the_two_reporting_checks_are_info_whether_or_not_they_found_anything(
    tmp_path, monkeypatch
):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)
    stock(tmp_path, VID)

    rows = {row["check"]: row for row in lint.diagnose(tmp_path, wiki)}
    assert rows["unfiled"]["status"] == lint.INFO
    assert rows["orphans"]["status"] == lint.INFO
    assert all(rows[name]["status"] == lint.PASS for name in lint.CHECKS[:6])


def test_a_video_the_library_no_longer_holds_fails_the_filed_check(tmp_path, monkeypatch):
    all_links_hold(monkeypatch)
    wiki = filed_wiki(tmp_path)  # no library at all: the video is gone

    rows = {row["check"]: row for row in lint.diagnose(tmp_path, wiki)}
    assert rows["filed"]["status"] == lint.FAIL
    assert VID in rows["filed"]["detail"]


def test_a_detail_is_always_one_line_so_the_report_stays_a_column(tmp_path, monkeypatch):
    monkeypatch.setattr(seams, "verify", lambda home, text: "broke\nover\nlines")
    wiki = filed_wiki(tmp_path)

    rows = lint.diagnose(tmp_path, wiki)
    assert all("\n" not in row["detail"] for row in rows)
    report = lint.report(rows)
    assert len(report.splitlines()) == len(lint.CHECKS)
    columns = {line.index(row["status"]) for line, row in zip(report.splitlines(), rows)}
    assert len(columns) == 1, f"the status does not start at one column: {columns}"


def test_a_missing_wiki_is_a_usage_error_and_makes_nothing(tmp_path):
    with pytest.raises(Usage) as raised:
        lint.run(tmp_path, as_json=False)
    assert str(tmp_path / "wiki") in str(raised.value)
    assert not (tmp_path / "wiki").exists()
