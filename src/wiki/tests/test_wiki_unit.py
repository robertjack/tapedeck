"""Ephemeral unit tests for the wiki component's internals.

Disposable by design (phx): the durable acceptance criteria are
system/evals/wiki/, which drive `python -m wiki` and never import this package.
What is worth testing here is the part those evals can only reach through a
subprocess and a fake agent — the three grammars of the layout contract, the
gate's individual checks, the sweep's ordering rule — plus the streaming seam
added for SPEC-wiki-007, exercised directly against a small script rather than
through a whole `wiki file` run.

Run with: uv run --with pytest pytest src/wiki/tests -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from wiki import gate, layout, library, seams

FILED = "dQw4w9WgXcQ"
OTHER = "plainvide00"


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
    assert "Regeneration" not in known
    assert "notes/regeneration" not in known


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
    assert layout.targets(layout.DEFAULT_BRIEF) == []
    assert "youtube.com" not in layout.DEFAULT_BRIEF and "youtu.be" not in layout.DEFAULT_BRIEF
    assert layout.DEFAULT_BRIEF.strip()


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
        assert name in said


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


def test_the_brief_is_compared_byte_for_byte(tmp_path):
    wiki = wiki_with(tmp_path)
    before = gate.snapshot(wiki)
    assert gate.brief_kept(wiki, before) == []
    (wiki / layout.BRIEF).write_text(layout.DEFAULT_BRIEF + "\n- one more rule\n")
    problems = gate.brief_kept(wiki, before)
    assert problems and layout.BRIEF in problems[0]


def test_the_filing_marker_must_exist_and_cite_its_own_recording(tmp_path):
    wiki = wiki_with(tmp_path)
    assert "does not exist" in gate.marker_written(wiki, FILED)[0]
    (wiki / "sources" / f"{FILED}.md").write_text(
        f"[here](https://www.youtube.com/watch?v={FILED}&t=95s)"
    )
    assert gate.marker_written(wiki, FILED) == []


# --- seams: the streaming maintainer (SPEC-wiki-007) ---------------------------


def _script(tmp_path, body: str) -> str:
    path = tmp_path / "maintainer.sh"
    path.write_text("#!/bin/sh\n" + body)
    return f"sh {path}"


def test_the_default_command_streams_by_default():
    assert "--output-format stream-json --verbose" in seams.DEFAULT_MAINTAINER_COMMAND


def test_event_parses_only_json_objects_carrying_a_type():
    assert seams._event('{"type": "result", "result": "ok"}') == {
        "type": "result",
        "result": "ok",
    }
    assert seams._event("plain prose, not json") is None
    assert seams._event('{"no_type": true}') is None
    assert seams._event("") is None


def test_touched_prefers_file_path_over_other_keys():
    assert seams._touched({"file_path": "notes/a.md", "pattern": "x"}) == "notes/a.md"
    assert seams._touched({"pattern": "*.md"}) == "*.md"
    assert seams._touched({}) == ""


@needs_git
def test_a_streaming_maintainer_yields_live_progress_and_a_result_product(tmp_path, capsys):
    body = (
        'cat > /dev/null\n'
        'echo \'{"type":"system","subtype":"init","model":"fixture-model-9"}\'\n'
        'echo \'{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Read","input":{"file_path":"sources/probe.md"}}]}}\'\n'
        'echo \'{"type":"result","subtype":"success","result":"all done"}\'\n'
    )
    command = _script(tmp_path, body)
    code, product = seams.run_maintainer(command, tmp_path, tmp_path, "task text", "filing X")
    err = capsys.readouterr().err
    assert code == 0
    assert product == "all done", "the product of a streamed run is the result event's text"
    assert "filing X" in err, "the run announces itself before the agent speaks"
    assert "fixture-model-9" in err
    assert "Read" in err and "sources/probe.md" in err
    assert '"type"' not in capsys.readouterr().out


@needs_git
def test_a_plain_maintainer_keeps_its_raw_stdout_as_the_product(tmp_path):
    command = _script(tmp_path, "cat > /dev/null\necho 'plain findings, not json'\n")
    code, product = seams.run_maintainer(command, tmp_path, tmp_path, "task text", "tending")
    assert code == 0
    assert "plain findings, not json" in product


@needs_git
def test_a_nonzero_exit_is_reported_with_whatever_product_there_was(tmp_path):
    command = _script(tmp_path, "cat > /dev/null\necho 'partial'\nexit 3\n")
    code, product = seams.run_maintainer(command, tmp_path, tmp_path, "task text", "tending")
    assert code == 3
    assert "partial" in product


@needs_git
def test_the_task_reaches_the_maintainer_on_stdin_without_deadlocking(tmp_path):
    """Stdin is fed on its own thread precisely so a large task cannot deadlock
    against a maintainer that starts writing before it has finished reading."""
    out = tmp_path / "seen"
    command = _script(tmp_path, f'cat > "{out}"\n')
    big_task = "line\n" * 20000  # comfortably past a single pipe buffer
    code, _ = seams.run_maintainer(command, tmp_path, tmp_path, big_task, "filing X")
    assert code == 0
    assert out.read_text() == big_task
