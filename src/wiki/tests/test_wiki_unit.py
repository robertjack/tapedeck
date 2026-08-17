"""Ephemeral unit tests for the wiki component's internals.

Disposable by design (phx): the durable acceptance criteria are
system/evals/wiki/, which drive `python -m wiki` and never import this package.
What is worth testing here is the part those evals can only reach through a
subprocess and a fake agent — the layout grammars, the gate's individual checks,
the sweep's ordering rule, the streaming seam's cost parsing, and the SPEC-wiki-008
bookkeeping reconciliation added this round.

Run with: uv run --with pytest pytest src/wiki/tests -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from wiki import bookkeeping, gate, layout, library, seams

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
        "## [2026-01-02] file | dQw4w9WgXcQ\n\nprose\n\n"
        "## [not-a-date] file | broken\n"
    )
    assert layout.entries(log) == [("file", "dQw4w9WgXcQ")]
    assert layout.malformed(log) == ["## [not-a-date] file | broken"]


def test_cites_asks_only_whether_the_deep_link_form_appears():
    assert layout.cites(f"see https://www.youtube.com/watch?v={FILED}&t=1s", FILED)
    assert not layout.cites("no links here", FILED)
    assert not layout.cites(f"watch?v={OTHER}", FILED)


def test_opening_heading_is_the_first_hash_line_or_none():
    assert layout.opening_heading("# Regeneration\n\nprose") == "Regeneration"
    assert layout.opening_heading("some text\n# Later\n") == "Later"
    assert layout.opening_heading("no headings here") is None
    assert layout.opening_heading("#\nprose") is None


def test_catalog_reads_only_markdown_dot_md_links():
    text = (
        "- [Sources](sources/x.md) — a page\n"
        "- [External](https://example.com)\n"
        "- [Anchor](notes/y.md#section)\n"
    )
    assert layout.catalog(text) == ["sources/x.md", "notes/y.md"]


# --- bookkeeping: SPEC-wiki-008 reconciliation ---------------------------------


def test_reconcile_catalog_appends_missing_pages_with_their_own_heading(tmp_path):
    wiki = wiki_with(
        tmp_path,
        sources__vid00000001="# vid00000001\n\ncited already\n",
        notes__proofing="# Proofing times\n\nbody\n",
    )
    (wiki / layout.INDEX).write_text("- [vid00000001](sources/vid00000001.md)\n")
    bookkeeping.reconcile_catalog(wiki)
    text = (wiki / layout.INDEX).read_text()
    assert text.startswith("- [vid00000001](sources/vid00000001.md)\n"), (
        "the existing line must survive untouched — appended to, never regenerated"
    )
    assert "- [Proofing times](notes/proofing.md)" in text


def test_reconcile_catalog_is_a_no_op_once_everything_is_listed(tmp_path):
    wiki = wiki_with(tmp_path, notes__only="# Only\n")
    (wiki / layout.INDEX).write_text("- [Only](notes/only.md)\n")
    before = (wiki / layout.INDEX).read_text()
    bookkeeping.reconcile_catalog(wiki)
    assert (wiki / layout.INDEX).read_text() == before


def test_reconcile_log_appends_a_fallback_entry_when_the_agent_wrote_nothing(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    bookkeeping.reconcile_log(wiki, before, "file", "", {}, FILED)
    op, subject = layout.entries(layout.read(wiki / layout.LOG))[0]
    assert op == "file"
    assert subject == FILED


def test_reconcile_log_uses_the_product_as_the_subject_and_records_cost(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    cost = {"duration_s": 90, "cost_usd": 0.42, "input_tokens": 31000, "output_tokens": 4200}
    bookkeeping.reconcile_log(wiki, before, "file", "filed the video", cost, FILED)
    text = layout.read(wiki / layout.LOG)
    assert layout.entries(text) == [("file", "filed the video")]
    for figure in ("90", "0.42", "31000", "4200"):
        assert figure in text


def test_reconcile_log_leaves_an_agents_own_entry_alone(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    (wiki / layout.LOG).write_text(before.decode() + "## [2026-01-01] file | mine\n")
    bookkeeping.reconcile_log(wiki, before, "file", "tapedeck's own text", {}, FILED)
    assert layout.entries(layout.read(wiki / layout.LOG)) == [("file", "mine")]


def test_reconcile_log_never_writes_onto_a_broken_append_only_log(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes() + b"## [2026-01-01] file | x\n"
    (wiki / layout.LOG).write_text("# rewritten from scratch\n")
    bookkeeping.reconcile_log(wiki, before, "file", "product", {}, FILED)
    assert (wiki / layout.LOG).read_text() == "# rewritten from scratch\n"


def test_no_cost_figures_means_no_cost_line_at_all(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    bookkeeping.reconcile_log(wiki, before, "file", "quiet run", {}, FILED)
    text = layout.read(wiki / layout.LOG)
    assert "0.0" not in text and "$0" not in text


# --- gate: the individual checks -----------------------------------------------


def test_brief_kept_fails_only_on_a_byte_difference(tmp_path):
    wiki = wiki_with(tmp_path)
    before = gate.snapshot(wiki)
    assert gate.brief_kept(wiki, before) == []
    (wiki / layout.BRIEF).write_text(layout.DEFAULT_BRIEF + "x")
    assert gate.brief_kept(wiki, before) != []


def test_marker_written_requires_the_page_and_its_own_citation(tmp_path):
    wiki = wiki_with(tmp_path)
    assert gate.marker_written(wiki, FILED) != []
    (wiki / "sources" / f"{FILED}.md").write_text("no citation here")
    assert gate.marker_written(wiki, FILED) != []
    (wiki / "sources" / f"{FILED}.md").write_text(f"watch?v={FILED}")
    assert gate.marker_written(wiki, FILED) == []


def test_sources_kept_flags_only_a_removed_source_page(tmp_path):
    wiki = wiki_with(tmp_path, sources__a=f"watch?v={FILED}")
    before = gate.snapshot(wiki)
    (wiki / "sources" / "a.md").unlink()
    assert gate.sources_kept(wiki, before) != []


def test_unresolved_names_the_dangling_target(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="[[nowhere]]")
    problems = gate.unresolved(wiki, layout.pages(wiki))
    assert any("nowhere" in problem for problem in problems)


# --- library: selection and order ----------------------------------------------


def test_eligible_orders_by_upload_date_then_id(home):
    add_video(home, "bbbbbbbbbbb", "2020-01-01")
    add_video(home, "aaaaaaaaaaa", "2020-01-01")
    add_video(home, "ccccccccccc", "2019-01-01")
    assert library.eligible(home) == ["ccccccccccc", "aaaaaaaaaaa", "bbbbbbbbbbb"]


def test_eligible_skips_and_explains_what_it_cannot_file(home):
    add_video(home, "aaaaaaaaaaa", "2020-01-01", media=False)
    add_video(home, "bbbbbbbbbbb", "2020-01-01", page=False)
    (home / "library" / "not-a-video-id").mkdir()
    notes = []
    found = library.eligible(home, note=notes.append)
    assert found == []
    assert len(notes) == 3


# --- seams: cost parsing and the config seam ------------------------------------


def test_maintainer_command_names_the_missing_key(tmp_path):
    with pytest.raises(Exception) as exc:
        seams.maintainer_command(tmp_path)
    assert "maintainer_command" in str(exc.value)


def test_cost_extraction_reads_only_what_is_present():
    full = seams._cost(
        {
            "duration_ms": 90000,
            "total_cost_usd": 0.42,
            "usage": {"input_tokens": 31000, "output_tokens": 4200},
        }
    )
    assert full == {
        "duration_s": 90,
        "cost_usd": 0.42,
        "input_tokens": 31000,
        "output_tokens": 4200,
    }
    assert seams._cost({"type": "result"}) == {}
    assert seams._cost(None) == {}


@needs_git
def test_run_maintainer_streams_progress_and_reports_cost(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    script = tmp_path / "maintainer.sh"
    script.write_text(
        "#!/bin/sh\ncat > /dev/null\n"
        'echo \'{"type":"result","subtype":"success","result":"done",'
        '"duration_ms":2000,"total_cost_usd":0.01,'
        '"usage":{"input_tokens":10,"output_tokens":5}}\'\n'
    )
    script.chmod(0o755)
    code, product, cost = seams.run_maintainer(str(script), tmp_path, wiki, "task", "label")
    assert code == 0
    assert product == "done"
    assert cost == {"duration_s": 2, "cost_usd": 0.01, "input_tokens": 10, "output_tokens": 5}


@needs_git
def test_run_maintainer_treats_non_json_stdout_as_the_raw_product(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    script = tmp_path / "maintainer.sh"
    script.write_text("#!/bin/sh\ncat > /dev/null\necho 'plain prose'\n")
    script.chmod(0o755)
    code, product, cost = seams.run_maintainer(str(script), tmp_path, wiki, "task", "label")
    assert code == 0
    assert product.strip() == "plain prose"
    assert cost == {}
