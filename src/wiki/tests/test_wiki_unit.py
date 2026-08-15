"""Ephemeral unit tests for wiki — disposable, unlike system/evals/wiki.

The durable evals drive `python -m wiki file <id>` and judge the wiki that comes out.
These poke at the pieces underneath: each gate check on its own, the scaffold's
refusal to rewrite anything, the git lifecycle's promise that "back" means the pre-run
commit including untracked work, and the two seams' resolution.
"""

from __future__ import annotations

import subprocess

import pytest

from wiki import gate, repo, scaffold, seams
from wiki.__main__ import Failure, main

VID = "dQw4w9WgXcQ"
OTHER = "plainvide00"
LINK = f"https://www.youtube.com/watch?v={VID}&t=95s"
ENTRY = "## [2026-08-14] file | " + VID


@pytest.fixture
def wiki(tmp_path):
    """A scaffolded wiki with one filed video, committed — the pre-run shape."""
    root = tmp_path / "wiki"
    scaffold.ensure(root)
    (root / "sources" / f"{VID}.md").write_text(f"# {VID}\n\nSee [it]({LINK}).\n")
    (root / "notes" / "idea.md").write_text("# Idea\n\nFrom [[dQw4w9WgXcQ]].\n")
    (root / "index.md").write_text(
        f"- [{VID}](sources/{VID}.md)\n- [Idea](notes/idea.md)\n"
    )
    (root / "log.md").write_text(f"{ENTRY}\n\nFiled it.\n")
    repo.open_repo(root)
    repo.commit(root, "fixture")
    return root


def before_of(wiki, log=b""):
    """The pre-run snapshot. The chronology defaults to empty so the fixture's one
    entry reads as the entry this operation added."""
    return {"CLAUDE.md": (wiki / "CLAUDE.md").read_bytes(), "log.md": log}


def review(wiki, monkeypatch, video_id=VID, before=None):
    """The gate with ask stubbed out — its verdict has its own evals."""
    monkeypatch.setattr(seams, "ask_verify", lambda home, text: None)
    return gate.review(wiki, wiki.parent, video_id, before_of(wiki) if before is None else before)


# --- the scaffold -----------------------------------------------------------


def test_scaffold_creates_the_five_pinned_entries(tmp_path):
    root = tmp_path / "wiki"
    assert scaffold.ensure(root) is True
    assert (root / "sources").is_dir() and (root / "notes").is_dir()
    assert (root / "CLAUDE.md").read_text().strip()
    assert (root / "index.md").read_text() == ""
    assert (root / "log.md").read_text() == ""


def test_scaffold_never_rewrites_what_is_already_there(tmp_path):
    root = tmp_path / "wiki"
    scaffold.ensure(root)
    mine = "# My rules\n"
    (root / "CLAUDE.md").write_text(mine)
    (root / "log.md").write_text("history\n")

    assert scaffold.ensure(root) is False
    assert (root / "CLAUDE.md").read_text() == mine
    assert (root / "log.md").read_text() == "history\n"


def test_the_default_brief_carries_no_link_the_gate_would_reject(tmp_path):
    """It is a page like any other to the gate that reads it, so an example wikilink
    or an example deep link in it would fail every filing until someone deleted it."""
    root = tmp_path / "wiki"
    scaffold.ensure(root)
    brief = (root / "CLAUDE.md").read_text()
    assert not gate.WIKILINK.search(brief)
    assert "https://" not in brief and "http://" not in brief


# --- the gate, one check at a time ------------------------------------------


def test_a_clean_wiki_has_nothing_wrong_with_it(wiki, monkeypatch):
    assert review(wiki, monkeypatch) == []


def test_an_edited_brief_is_named(wiki, monkeypatch):
    before = before_of(wiki)
    (wiki / "CLAUDE.md").write_text("rewritten by the agent\n")
    assert any("CLAUDE.md" in p for p in review(wiki, monkeypatch, before=before))


def test_a_missing_sources_page_is_named(wiki, monkeypatch):
    (wiki / "sources" / f"{VID}.md").unlink()
    (wiki / "index.md").write_text("- [Idea](notes/idea.md)\n")
    (wiki / "notes" / "idea.md").write_text("# Idea\n")
    problems = review(wiki, monkeypatch)
    assert any(f"sources/{VID}.md" in p for p in problems), problems


def test_a_sources_page_citing_only_another_video_is_named(wiki, monkeypatch):
    page = wiki / "sources" / f"{VID}.md"
    page.write_text(f"# {VID}\n\nSee [it](https://www.youtube.com/watch?v={OTHER}&t=5s).\n")
    assert any(VID in p and "deep link" in p for p in review(wiki, monkeypatch))


def test_a_deep_link_is_read_by_asks_rules_not_a_second_regex(wiki, monkeypatch):
    """A citation ending a sentence is a citation: the full stop is prose. This holds
    only because the reading is imported from ask (LESSON-0003)."""
    page = wiki / "sources" / f"{VID}.md"
    page.write_text(f"# {VID}\n\nSaid so [here]({LINK}).\n")
    assert review(wiki, monkeypatch) == []


@pytest.mark.parametrize(
    "link, broken",
    [("[[nowhere]]", "nowhere"), ("[[Idea]]", "Idea"), ("[[nowhere|an alias]]", "nowhere")],
)
def test_an_unresolved_wikilink_is_named(wiki, monkeypatch, link, broken):
    page = wiki / "sources" / f"{VID}.md"
    page.write_text(page.read_text() + f"\nAlso {link}.\n")
    assert any(f"[[{broken}]]" in p for p in review(wiki, monkeypatch))


def test_an_aliased_wikilink_resolves_on_the_text_before_the_pipe(wiki, monkeypatch):
    page = wiki / "sources" / f"{VID}.md"
    page.write_text(page.read_text() + "\nAlso [[idea|the thought behind it]].\n")
    assert review(wiki, monkeypatch) == []


def test_a_page_the_catalog_forgot_is_named(wiki, monkeypatch):
    (wiki / "notes" / "stray.md").write_text("# Stray\n")
    assert any("stray" in p for p in review(wiki, monkeypatch))


def test_the_three_pinned_files_are_never_owed_a_catalog_line(wiki, monkeypatch):
    assert not any("index.md is a stray" in p for p in review(wiki, monkeypatch))


def test_a_non_markdown_file_is_not_a_page(wiki, monkeypatch):
    (wiki / "notes" / "diagram.png").write_bytes(b"\x89PNG")
    assert review(wiki, monkeypatch) == []


def test_a_rewritten_log_is_named(wiki, monkeypatch):
    log = wiki / "log.md"
    before = before_of(wiki, log.read_bytes())
    log.write_text(f"# Tidied\n\n{ENTRY}\n")
    assert any("rewritten" in p for p in review(wiki, monkeypatch, before=before))


def test_a_log_that_gained_no_entry_is_named(wiki, monkeypatch):
    log = wiki / "log.md"
    before = before_of(wiki, log.read_bytes())
    log.write_text(log.read_text() + "filed another one\n")
    assert any("pinned shape" in p for p in review(wiki, monkeypatch, before=before))


def test_an_entry_appended_mid_line_does_not_count(wiki, monkeypatch):
    """A heading only begins an entry at the start of a line, and the entry has to be
    in what this run added — searching the whole file would let an operation that
    wrote nothing coast on the entry before it."""
    log = wiki / "log.md"
    log.write_text(f"{ENTRY}\n\nFiled it.")  # deliberately unterminated
    before = before_of(wiki, log.read_bytes())
    log.write_text(log.read_text() + f" {ENTRY}\n")
    assert any("pinned shape" in p for p in review(wiki, monkeypatch, before=before))


def test_every_independent_failure_is_reported(wiki, monkeypatch):
    before = before_of(wiki)
    (wiki / "CLAUDE.md").write_text("mine now\n")
    (wiki / "notes" / "stray.md").write_text("# Stray\n\n[[nowhere]]\n")
    problems = review(wiki, monkeypatch, before=before)
    assert any("CLAUDE.md" in p for p in problems)
    assert any("stray" in p for p in problems)
    assert any("nowhere" in p for p in problems)


def test_asks_words_are_the_ones_reported(wiki, monkeypatch):
    monkeypatch.setattr(seams, "ask_verify", lambda home, text: "unverifiable: t=9999s")
    problems = gate.review(wiki, wiki.parent, VID, before_of(wiki))
    assert any("unverifiable: t=9999s" in p for p in problems)


# --- git ---------------------------------------------------------------------


def git(wiki, *args):
    return subprocess.run(["git", *args], cwd=wiki, capture_output=True, text=True)


def test_restore_removes_untracked_work_as_well_as_tracked(wiki):
    pre_run = repo.head(wiki)
    (wiki / "notes" / "half.md").write_text("half a thought\n")
    (wiki / "index.md").write_text("clobbered\n")

    repo.restore(wiki, pre_run)
    assert not (wiki / "notes" / "half.md").exists()
    assert "notes/idea.md" in (wiki / "index.md").read_text()
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_dirty_sees_a_hand_edit_and_a_commit_clears_it(wiki):
    assert not repo.dirty(wiki)
    (wiki / "notes" / "idea.md").write_text("mine\n")
    assert repo.dirty(wiki)
    repo.commit(wiki, "user edits")
    assert not repo.dirty(wiki)
    assert git(wiki, "log", "--format=%s").stdout.splitlines()[0] == "user edits"


def test_open_repo_is_idempotent_and_never_adopts_a_parent(tmp_path):
    outer = tmp_path / "outer"
    (outer / "wiki").mkdir(parents=True)
    assert git(outer, "init", "-q").returncode == 0
    inner = outer / "wiki"
    scaffold.ensure(inner)
    repo.open_repo(inner)
    repo.open_repo(inner)
    top = git(inner, "rev-parse", "--show-toplevel").stdout.strip()
    assert top.endswith("wiki"), top


# --- the seams ---------------------------------------------------------------


def test_a_missing_maintainer_key_names_it(tmp_path):
    (tmp_path / "config.toml").write_text("[ask]\nanswerer_command = 'x'\n")
    with pytest.raises(seams.ConfigError) as caught:
        seams.maintainer_command(tmp_path)
    assert "maintainer_command" in str(caught.value)


def test_an_empty_maintainer_command_is_no_command(tmp_path):
    (tmp_path / "config.toml").write_text("[wiki]\nmaintainer_command = '   '\n")
    with pytest.raises(seams.ConfigError):
        seams.maintainer_command(tmp_path)


def test_unreadable_config_is_a_usage_error(tmp_path):
    (tmp_path / "config.toml").write_text("this is not toml = = =\n")
    with pytest.raises(seams.ConfigError):
        seams.maintainer_command(tmp_path)


def test_the_published_default_reads_the_library_and_writes_the_wiki():
    assert "acceptEdits" in seams.DEFAULT_MAINTAINER_COMMAND
    for tool in ("Read", "Grep", "Glob", "Write", "Edit"):
        assert tool in seams.DEFAULT_MAINTAINER_COMMAND
    assert "Bash" not in seams.DEFAULT_MAINTAINER_COMMAND


def test_a_maintainer_that_exits_nonzero_is_a_failed_operation(tmp_path):
    with pytest.raises(seams.MaintainerFailed):
        seams.run_maintainer("exit 4", tmp_path, tmp_path, VID, tmp_path / "p.md", "task")


def test_ask_is_reached_through_the_documented_override(tmp_path, monkeypatch):
    script = tmp_path / "fake-ask.sh"
    script.write_text('#!/bin/sh\n{ echo "$*"; cat; } > "$TAPEDECK_HOME/seen"\n')
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")

    assert seams.ask_verify(tmp_path, "text with a link") is None
    seen = (tmp_path / "seen").read_text()
    assert seen.splitlines()[0] == "verify"
    assert "--require-citation" not in seen
    assert "text with a link" in seen


def test_what_ask_says_about_a_bad_link_is_relayed(tmp_path, monkeypatch):
    script = tmp_path / "fake-ask.sh"
    script.write_text('#!/bin/sh\ncat >/dev/null\necho "unverifiable: past the end" >&2\nexit 1\n')
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")
    assert seams.ask_verify(tmp_path, "text") == "unverifiable: past the end"


# --- the refusals that cost nothing -------------------------------------------


def test_a_malformed_id_never_reaches_the_config(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    assert main(["file", "not-an-id"]) == 2
    assert not (tmp_path / "wiki").exists()


def test_an_unknown_video_is_a_usage_error(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    (tmp_path / "library").mkdir()
    assert main(["file", OTHER]) == 2


def test_a_video_without_an_archive_page_is_an_operation_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    (tmp_path / "library" / VID).mkdir(parents=True)
    assert main(["file", VID]) == 1


def test_failure_carries_its_own_exit_code():
    assert Failure("x").code == 1
    assert Failure("x", 2).code == 2
