"""Ephemeral unit tests for the wiki component's internals.

Disposable by design (phx): the durable acceptance criteria are
system/evals/wiki/, which drive `python -m wiki` and never import this package.
What is worth testing here is the part those evals can only reach through a
subprocess and a fake agent — the three grammars of the layout contract, the
gate's individual checks, the sweep's ordering rule, and the shape of the lint
report — so a regression shows up as one failing assertion instead of a rejected
filing.

Run with: uv run --with pytest pytest src/wiki/tests -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from wiki import Busy, Usage, gate, layout, library, lint, repo, seams

FILED = "dQw4w9WgXcQ"
OTHER = "plainvide00"


# --- fixtures -----------------------------------------------------------------


def git_available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


needs_git = pytest.mark.skipif(not git_available(), reason="git is not installed")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    (h / "archive").mkdir()
    return h


def add_video(home: Path, video_id: str, upload_date: str, media: bool = True, page: bool = True):
    entry = home / "library" / video_id
    entry.mkdir(parents=True)
    if media:
        (entry / "video.mp4").write_bytes(b"\x00")
    (entry / "meta.json").write_text(
        json.dumps({"id": video_id, "title": video_id, "upload_date": upload_date})
    )
    if page:
        (home / "archive" / f"{video_id}.md").write_text(f"# {video_id}\n")


def wiki_with(tmp_path, **files) -> Path:
    wiki = tmp_path / "wiki"
    (wiki / "sources").mkdir(parents=True)
    (wiki / "notes").mkdir()
    (wiki / layout.BRIEF).write_text(layout.DEFAULT_BRIEF)
    (wiki / layout.INDEX).write_text("")
    (wiki / layout.LOG).write_text("")
    for name, text in files.items():
        path = wiki / (name.replace("__", "/") + layout.PAGE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return wiki


# --- layout: the three grammars ------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("[[thing]]", ["thing"]),
        ("[[thing|an alias]]", ["thing"]),
        ("[[ spaced ]]", ["spaced"]),
        ("[[a]] and [[b|B]]", ["a", "b"]),
        ("nothing here", []),
        ("[not a wikilink](x.md)", []),
    ],
)
def test_wikilink_targets_are_the_text_before_the_first_pipe(text, expected):
    assert layout.targets(text) == expected


def test_wikilink_resolution_is_case_sensitive_and_path_free(tmp_path):
    wiki = wiki_with(tmp_path, sources__dQw4w9WgXcQ="x", notes__regeneration="y")
    known = layout.resolvable(layout.pages(wiki))
    assert "regeneration" in known and "dQw4w9WgXcQ" in known
    assert "Regeneration" not in known, "a link that works in one reader and not another"
    assert "notes/regeneration" not in known, "no paths, no extensions, no fuzzy match"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("- [X](sources/x.md)", ["sources/x.md"]),
        ("- [X](./notes/x.md) — a summary", ["notes/x.md"]),
        ("- [X](notes/x.md#heading)", ["notes/x.md"]),
        ("- [Home](https://example.com/x.md)", []),
        ("- [X](sources/x.txt)", []),
    ],
)
def test_the_catalog_reads_markdown_links_to_pages_only(line, expected):
    assert layout.catalog(line) == expected


def test_log_entries_and_malformed_headings_are_the_pinned_shape():
    log = (
        "## [2026-08-15] file | dQw4w9WgXcQ\n\nprose\n\n"
        "## [2026-08-16] tend | connected two notes\n\n"
        "## [not-a-date] file missing-the-pipe\n"
    )
    assert layout.entries(log) == [
        ("file", "dQw4w9WgXcQ"),
        ("tend", "connected two notes"),
    ]
    assert layout.malformed(log) == ["## [not-a-date] file missing-the-pipe"]


def test_the_default_brief_is_a_page_the_gate_can_accept():
    """CLAUDE.md is a page like any other and the gate reads every page. A wiki
    link written out in the brief would have to resolve to a page that does not
    exist, and a YouTube URL written out in it would be read as a citation and
    checked against the library — either one would reject every filing ever made
    against a freshly scaffolded wiki."""
    assert layout.targets(layout.DEFAULT_BRIEF) == [], (
        "the scaffolded brief carries a wiki link that resolves to nothing"
    )
    assert "youtube.com" not in layout.DEFAULT_BRIEF and "youtu.be" not in layout.DEFAULT_BRIEF, (
        "the scaffolded brief carries a URL that ask will read as a fabricated citation"
    )
    assert layout.DEFAULT_BRIEF.strip(), "the brief is scaffolded with defaults"


def test_a_page_cites_the_video_it_names_in_the_layouts_format():
    assert layout.cites(f"see [it](https://www.youtube.com/watch?v={FILED}&t=95s).", FILED)
    assert not layout.cites(f"watch?v={OTHER}&t=95s", FILED)
    assert not layout.cites("no link at all", FILED)


# --- library: eligibility and sweep order --------------------------------------


def test_the_sweep_orders_by_upload_date_then_id(home):
    add_video(home, "tie-zebra-2", "2023-05-05")
    add_video(home, "middle00002", "2021-07-09")
    add_video(home, "tie-alpha-1", "2023-05-05")
    add_video(home, "oldest00001", "2019-03-04")

    assert library.eligible(home) == [
        "oldest00001",
        "middle00002",
        "tie-alpha-1",
        "tie-zebra-2",
    ]


def test_entries_a_filing_could_not_be_attempted_on_are_skipped_with_a_note(home):
    add_video(home, "goodvideo01", "2020-01-01")
    add_video(home, "medialess01", "2020-01-02", media=False)
    add_video(home, "unrendered1", "2020-01-03", page=False)
    (home / "library" / "reading-notes").mkdir()

    notes = []
    assert library.eligible(home, note=notes.append) == ["goodvideo01"]
    said = "\n".join(notes)
    for name in ("medialess01", "unrendered1", "reading-notes"):
        assert name in said, f"a skip the user cannot see is one they will never fix: {said}"
    for note in notes:
        # `summary_line` in the durable evals finds the sweep's one-line summary by
        # looking for filed/skip/fail together; a skip note must never look like it.
        assert not ("filed" in note and "fail" in note), note


def test_an_unreadable_meta_sorts_first_and_stays_eligible(home):
    add_video(home, "goodvideo01", "2020-01-01")
    add_video(home, "brokenmeta1", "2020-01-02")
    (home / "library" / "brokenmeta1" / "meta.json").write_text("{ not json")

    assert library.eligible(home) == ["brokenmeta1", "goodvideo01"]


# --- the gate's individual checks ----------------------------------------------


def test_unresolved_names_the_page_and_the_target(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="See [[b]] and [[nowhere]].", notes__b="b")
    problems = gate.unresolved(wiki, layout.pages(wiki))
    assert len(problems) == 1
    assert "nowhere" in problems[0] and "notes/a.md" in problems[0]


def test_uncatalogued_ignores_the_three_pinned_files(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="a", notes__b="b")
    (wiki / layout.INDEX).write_text("- [A](notes/a.md)\n")

    assert gate.uncatalogued(wiki, layout.pages(wiki)) == ["notes/b.md"]


def test_dangling_finds_catalog_lines_with_nothing_behind_them(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="a")
    (wiki / layout.INDEX).write_text("- [A](notes/a.md)\n- [Ghost](notes/ghost.md)\n")

    assert gate.dangling(wiki) == ["notes/ghost.md"]


def test_the_brief_is_compared_byte_for_byte(tmp_path):
    wiki = wiki_with(tmp_path)
    before = gate.snapshot(wiki)
    assert gate.brief_kept(wiki, before) == []

    (wiki / layout.BRIEF).write_text(layout.DEFAULT_BRIEF + "\n- one more rule\n")
    problems = gate.brief_kept(wiki, before)
    assert problems and layout.BRIEF in problems[0]


def test_the_chronology_must_grow_at_the_end_and_gain_an_entry(tmp_path):
    wiki = wiki_with(tmp_path)
    (wiki / layout.LOG).write_text("## [2026-08-15] file | dQw4w9WgXcQ\n")
    before = gate.snapshot(wiki)

    (wiki / layout.LOG).write_text("# tidied\n## [2026-08-15] file | dQw4w9WgXcQ\n")
    assert "append-only" in gate.chronology(wiki, before)[0]

    (wiki / layout.LOG).write_text(
        "## [2026-08-15] file | dQw4w9WgXcQ\nfiled another one\n"
    )
    assert "gained no entry" in gate.chronology(wiki, before)[0]

    (wiki / layout.LOG).write_text(
        "## [2026-08-15] file | dQw4w9WgXcQ\n\n## [2026-08-16] file | plainvide00\n"
    )
    assert gate.chronology(wiki, before) == []


def test_the_filing_marker_must_exist_and_cite_its_own_recording(tmp_path):
    wiki = wiki_with(tmp_path)
    assert "does not exist" in gate.marker_written(wiki, FILED)[0]

    (wiki / "sources" / f"{FILED}.md").write_text(
        f"# {FILED}\n\nSame ground as [the other](https://www.youtube.com/watch?v={OTHER}&t=95s).\n"
    )
    problems = gate.marker_written(wiki, FILED)
    assert problems and FILED in problems[0]

    (wiki / "sources" / f"{FILED}.md").write_text(
        f"[here](https://www.youtube.com/watch?v={FILED}&t=95s)"
    )
    assert gate.marker_written(wiki, FILED) == []


def test_a_source_page_may_not_be_deleted_or_renamed_away(tmp_path):
    wiki = wiki_with(tmp_path, sources__dQw4w9WgXcQ="x")
    before = gate.snapshot(wiki)
    assert gate.sources_kept(wiki, before) == []

    (wiki / "sources" / f"{FILED}.md").rename(wiki / "notes" / f"{FILED}.md")
    problems = gate.sources_kept(wiki, before)
    assert problems and f"sources/{FILED}.md" in problems[0]


# --- the seams -----------------------------------------------------------------


def test_a_missing_maintainer_seam_names_the_key(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(Usage) as absent:
        seams.maintainer_command(home)
    assert seams.MAINTAINER_KEY in str(absent.value)

    (home / "config.toml").write_text('[wiki]\nmaintainer_command = "   "\n')
    with pytest.raises(Usage) as blank:
        seams.maintainer_command(home)
    assert seams.MAINTAINER_KEY in str(blank.value)

    (home / "config.toml").write_text('[wiki]\nmaintainer_command = "claude -p"\n')
    assert seams.maintainer_command(home) == "claude -p"


def test_ask_is_reached_by_its_published_verb_without_require_citation(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    record = home / "ask-calls"
    script = home / "fake-ask.sh"
    script.write_text(
        f'#!/bin/sh\n{{ echo "argv: $*"; cat; }} >> "{record}"\n'
    )
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")

    assert seams.unverifiable(home, "a page with a link") is None
    argv = record.read_text().splitlines()[0]
    assert seams.VERIFY in argv and "--require-citation" not in argv


def test_asks_own_words_are_what_the_caller_relays(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    script = home / "fake-ask.sh"
    script.write_text('#!/bin/sh\ncat > /dev/null\necho "unverifiable citation" >&2\nexit 1\n')
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")

    assert seams.unverifiable(home, "text") == "unverifiable citation"


def test_the_tender_is_handed_no_video_id(tmp_path, monkeypatch):
    home = tmp_path / "home"
    wiki = home / "wiki"
    wiki.mkdir(parents=True)
    record = home / "seen"
    script = home / "agent.sh"
    script.write_text(
        f'#!/bin/sh\n{{ pwd; echo "id=[$TAPEDECK_VIDEO_ID]"; echo "wiki=$TAPEDECK_WIKI"; cat; }}'
        f' > "{record}"\n'
    )
    monkeypatch.setenv("TAPEDECK_VIDEO_ID", "leaked00001")  # must not survive

    code, _ = seams.run_maintainer(f"sh {script}", home, wiki, "the task")
    assert code == 0
    seen = record.read_text().splitlines()
    assert Path(seen[0]).resolve() == wiki.resolve()
    assert seen[1] == "id=[]", seen
    assert Path(seen[2].split("=", 1)[1]).resolve() == wiki.resolve()
    assert "the task" in record.read_text()


# --- the report ----------------------------------------------------------------


@needs_git
def test_the_lint_report_is_one_aligned_line_per_check(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    (home / "library").mkdir(parents=True)
    (home / "archive").mkdir()
    wiki = home / "wiki"
    wiki.mkdir()
    repo.ready(wiki)
    (wiki / "notes" / "a.md").write_text("Standing alone.")
    (wiki / layout.INDEX).write_text("- [A](notes/a.md)\n")

    script = home / "fake-ask.sh"
    script.write_text("#!/bin/sh\ncat > /dev/null\n")
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")

    assert lint.lint(home, as_json=False) == 0
    printed = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in printed] == list(lint.CHECKS)
    columns = {line.index(line.split()[1], len(line.split()[0])) for line in printed}
    assert len(columns) == 1, f"the status column drifts: {printed}"
    assert all(len(line.split(maxsplit=2)) == 3 for line in printed), (
        f"every check carries a reason, the passes included: {printed}"
    )
    assert "\x1b" not in "\n".join(printed)


@needs_git
def test_lint_json_and_the_human_report_agree(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    (home / "library").mkdir(parents=True)
    wiki = home / "wiki"
    wiki.mkdir()
    repo.ready(wiki)
    (wiki / "notes" / "a.md").write_text("Points at [[nowhere]].")
    (wiki / layout.INDEX).write_text("- [A](notes/a.md)\n")
    script = home / "fake-ask.sh"
    script.write_text("#!/bin/sh\ncat > /dev/null\n")
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")

    assert lint.lint(home, as_json=True) == 1, "a dangling link fails the run"
    rows = json.loads(capsys.readouterr().out)
    assert [row["check"] for row in rows] == list(lint.CHECKS)
    assert {row["status"] for row in rows} <= {"pass", "fail", "info"}
    assert all(row["detail"].strip() for row in rows)
    by_check = {row["check"]: row for row in rows}
    assert by_check["wikilinks"]["status"] == "fail"
    assert "nowhere" in by_check["wikilinks"]["detail"]
    assert by_check["orphans"]["status"] == "info", "info never decides the exit code"


def test_a_missing_wiki_is_a_usage_error_naming_the_path(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(Usage) as refused:
        lint.lint(home, as_json=False)
    assert str(home / "wiki") in str(refused.value)
    assert not (home / "wiki").exists()


# --- the repository ------------------------------------------------------------


@needs_git
def test_the_scaffold_is_one_commit_and_happens_once(tmp_path):
    wiki = tmp_path / "wiki"
    repo.ready(wiki)

    for name in layout.PINNED:
        assert (wiki / name).is_file()
    assert (wiki / "sources").is_dir() and (wiki / "notes").is_dir()
    assert (wiki / layout.INDEX).read_text() == ""
    assert repo.git(wiki, "rev-parse", "--show-toplevel").strip().endswith("wiki")
    assert len(repo.git(wiki, "log", "--format=%s").splitlines()) == 1

    mine = "# House rules\n"
    (wiki / layout.BRIEF).write_text(mine)
    repo.ready(wiki)
    assert (wiki / layout.BRIEF).read_text() == mine, "the brief is scaffolded once"


@needs_git
def test_a_directory_that_is_not_its_own_repository_is_not_versioned(tmp_path):
    outer = tmp_path / "outer"
    (outer / "wiki").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)

    assert not repo.versioned(outer / "wiki"), (
        "git searches upward; a wiki inside another repository must not be mistaken "
        "for one of its own, or a reset --hard would land in the enclosing repo"
    )


@needs_git
def test_restore_takes_untracked_work_with_it_and_keeps_the_shape(tmp_path):
    wiki = tmp_path / "wiki"
    repo.ready(wiki)
    before = repo.head(wiki)

    (wiki / "notes" / "half.md").write_text("half a thought")
    (wiki / layout.LOG).write_text("a tracked edit")
    repo.restore(wiki, before)

    assert not (wiki / "notes" / "half.md").exists(), "reset --hard alone leaves this"
    assert (wiki / layout.LOG).read_text() == "", "clean -fd alone leaves this"
    assert (wiki / "notes").is_dir() and (wiki / "sources").is_dir()


@needs_git
def test_pending_user_edits_become_the_pre_run_commit(tmp_path):
    wiki = tmp_path / "wiki"
    repo.ready(wiki)
    (wiki / "notes" / "mine.md").write_text("written by hand")

    pre_run = repo.commit_pending(wiki)
    assert repo.git(wiki, "log", "--format=%s").splitlines()[0] == repo.USER_EDITS
    assert not repo.dirty(wiki)

    (wiki / "notes" / "later.md").write_text("the agent's")
    repo.restore(wiki, pre_run)
    assert (wiki / "notes" / "mine.md").is_file(), "the rollback went back too far"
    assert not (wiki / "notes" / "later.md").exists()

    assert repo.commit_pending(wiki) == pre_run, "a clean tree commits nothing"


@needs_git
def test_one_operation_holds_the_wiki_at_a_time(tmp_path):
    wiki = tmp_path / "wiki"
    repo.ready(wiki)
    held = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time\n"
            "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "time.sleep(30)\n",
            str(wiki / ".git" / repo.LOCK),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert held.stdout.readline().strip() == "held"
        with pytest.raises(Busy) as refused:
            with repo.held(wiki):
                pass
        assert "another wiki operation" in str(refused.value)
    finally:
        held.kill()
        held.wait()

    with repo.held(wiki):  # released with the process that held it
        pass
