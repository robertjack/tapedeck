"""Ephemeral unit tests for the wiki component's internals.

Disposable by design (phx): the durable acceptance criteria are
system/evals/wiki/, which drive `python -m wiki` and never import this package.
What is worth testing here is the part those evals can only reach through a
subprocess and a fake agent — the layout grammars (including the SPEC-wiki-011
code-span exemption), the gate's individual checks, the sweep's ordering rule,
the streaming seam's cost parsing, the SPEC-wiki-008 bookkeeping reconciliation
(subject decoupled from product, cost as prose), the SPEC-wiki-009 map/shortlist,
the SPEC-wiki-010 staging-directory wording, and the SPEC-wiki-012 wait-vs-refuse
lock behavior.

Run with: uv run --with pytest pytest src/wiki/tests -q
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from wiki import bookkeeping, gate, layout, library, repo, seams, wikimap
from wiki import Busy

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


def test_a_wikilink_in_an_inline_code_span_is_not_a_link():
    text = "Pages point at each other with `[[nowhere]]`, which is just an example."
    assert layout.targets(text) == []


def test_a_wikilink_in_a_fenced_block_is_not_a_link():
    text = "See:\n\n```\n[[nowhere]]\n```\n\nabove is not a real link."
    assert layout.targets(text) == []


def test_a_wikilink_outside_code_still_resolves_normally():
    text = "`[[quoted]]` is code, but [[real]] is a claim."
    assert layout.targets(text) == ["real"]


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


def test_cites_asks_only_whether_the_videos_own_address_appears():
    url = f"https://www.youtube.com/watch?v={FILED}"
    assert layout.cites(f"see {url}&t=1s", url)
    assert not layout.cites("no links here", url)
    assert not layout.cites(f"https://www.youtube.com/watch?v={OTHER}&t=1s", url)


def test_cites_works_for_a_local_files_own_address_too():
    url = "file:///Users/somebody/Footage/standup.mp4"
    assert layout.cites(f"see [it]({url}?t=300s)", url)
    assert not layout.cites("file:///Users/somebody/Footage/other.mp4?t=10s", url)


def test_deep_link_form_appends_ampersand_or_question_mark_as_needed():
    assert layout.deep_link_form("https://www.youtube.com/watch?v=x").endswith(
        "&t=<seconds>s"
    )
    assert layout.deep_link_form("file:///a/b.mp4").endswith("?t=<seconds>s")


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


def test_the_default_brief_never_names_index_or_log_without_saying_tapedeck_keeps_them():
    """SPEC-wiki-008: the scaffolded brief must not read as an instruction to the
    maintainer to go and maintain either file."""
    for line in layout.DEFAULT_BRIEF.splitlines():
        for name in ("index.md", "log.md"):
            if name in line:
                assert "tapedeck" in line.lower(), line


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


def test_reconcile_log_uses_a_fixed_subject_never_the_product(tmp_path):
    """The bug this amendment removes: the subject used to be the product,
    squashed to one line, and a chatty run swallowed a whole paragraph into the
    heading. The subject is tapedeck's own regardless of what the agent said."""
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "Filed. Here's what landed.", {})
    op, subject = layout.entries(layout.read(wiki / layout.LOG))[0]
    assert op == "file"
    assert subject == FILED
    assert "Filed. Here's what landed." in layout.read(wiki / layout.LOG)


def test_reconcile_log_records_cost_as_a_prose_sentence(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    cost = {
        "duration_s": 90,
        "cost_usd": 0.42,
        "total_input_tokens": 931118,
        "cache_read_tokens": 900000,
        "output_tokens": 4200,
        "model": "fixture-model-9",
    }
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "filed the video", cost)
    text = layout.read(wiki / layout.LOG)
    assert layout.entries(text) == [("file", FILED)]
    for figure in ("90", "0.42", "931118", "900000", "4200", "fixture-model-9"):
        assert figure in text
    assert "118 in" not in text, (
        "the uncached remainder alone must never be reported as the run's input "
        "(SPEC-wiki-008, amended) — only the summed total"
    )
    assert "·" not in text, "the cost figures read as a sentence, not a status line"


def test_reconcile_log_leaves_an_agents_own_entry_alone(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    (wiki / layout.LOG).write_text(before.decode() + "## [2026-01-01] file | mine\n")
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "tapedeck's own text", {})
    assert layout.entries(layout.read(wiki / layout.LOG)) == [("file", "mine")]


def test_reconcile_log_never_writes_onto_a_broken_append_only_log(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes() + b"## [2026-01-01] file | x\n"
    (wiki / layout.LOG).write_text("# rewritten from scratch\n")
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "product", {})
    assert (wiki / layout.LOG).read_text() == "# rewritten from scratch\n"


def test_no_cost_figures_means_no_cost_sentence_at_all(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "quiet run", {})
    text = layout.read(wiki / layout.LOG)
    assert "0.0" not in text and "$0" not in text


def test_a_silent_product_still_gets_a_well_formed_entry(tmp_path):
    wiki = wiki_with(tmp_path)
    before = (wiki / layout.LOG).read_bytes()
    bookkeeping.reconcile_log(wiki, before, "file", FILED, "", {})
    op, subject = layout.entries(layout.read(wiki / layout.LOG))[0]
    assert (op, subject) == ("file", FILED)


def test_cost_sentence_omits_missing_figures_and_invents_nothing():
    assert bookkeeping.cost_sentence({}) is None
    assert bookkeeping.cost_sentence({"output_tokens": 5}) == "This run wrote 5 tokens."


# --- gate: the individual checks -----------------------------------------------


def test_brief_kept_fails_only_on_a_byte_difference(tmp_path):
    wiki = wiki_with(tmp_path)
    before = gate.snapshot(wiki)
    assert gate.brief_kept(wiki, before) == []
    (wiki / layout.BRIEF).write_text(layout.DEFAULT_BRIEF + "x")
    assert gate.brief_kept(wiki, before) != []


def test_marker_written_requires_the_page_and_its_own_citation(tmp_path):
    wiki = wiki_with(tmp_path)
    url = f"https://www.youtube.com/watch?v={FILED}"
    assert gate.marker_written(wiki, FILED, url) != []
    (wiki / "sources" / f"{FILED}.md").write_text("no citation here")
    assert gate.marker_written(wiki, FILED, url) != []
    (wiki / "sources" / f"{FILED}.md").write_text(f"{url}&t=1s")
    assert gate.marker_written(wiki, FILED, url) == []


def test_sources_kept_flags_only_a_removed_source_page(tmp_path):
    wiki = wiki_with(tmp_path, sources__a=f"watch?v={FILED}")
    before = gate.snapshot(wiki)
    (wiki / "sources" / "a.md").unlink()
    assert gate.sources_kept(wiki, before) != []


def test_unresolved_names_the_dangling_target(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="[[nowhere]]")
    problems = gate.unresolved(wiki, layout.pages(wiki))
    assert any("nowhere" in problem for problem in problems)


def test_unresolved_ignores_a_quoted_example(tmp_path):
    wiki = wiki_with(tmp_path, notes__a="see `[[nowhere]]` for the syntax")
    assert gate.unresolved(wiki, layout.pages(wiki)) == []


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


def test_eligible_calls_a_staging_directory_ours_and_names_the_video(home):
    """SPEC-wiki-010: a `.fetching-<id>-<random>` entry belongs to a download in
    progress, and the note must say so — never that it is foreign, a stray, or
    not tapedeck's — and must name the video being fetched."""
    (home / "library" / ".fetching-aaaaaaaaaaa-xyz123").mkdir()
    notes = []
    found = library.eligible(home, note=notes.append)
    assert found == []
    assert len(notes) == 1
    said = notes[0].lower()
    assert "aaaaaaaaaaa" in notes[0]
    for claim in ("not tapedeck's", "not tapedeck", "foreign", "stray", "someone else"):
        assert claim not in said, notes[0]


def test_eligible_still_calls_a_genuine_stranger_not_a_video_id(home):
    (home / "library" / "my-own-notes").mkdir()
    notes = []
    library.eligible(home, note=notes.append)
    assert any("my-own-notes" in note for note in notes)


# --- seams: cost parsing and the config seam ------------------------------------


def test_maintainer_command_names_the_missing_key(tmp_path):
    with pytest.raises(Exception) as exc:
        seams.maintainer_command(tmp_path)
    assert "maintainer_command" in str(exc.value)


def test_cost_extraction_sums_the_whole_usage_not_the_uncached_remainder():
    """The defect the amendment removes, pinned here too: `usage.input_tokens`
    alone is a rounding error next to what the cache absorbed."""
    full = seams._cost(
        {
            "duration_ms": 90000,
            "total_cost_usd": 0.42,
            "usage": {
                "input_tokens": 118,
                "output_tokens": 4200,
                "cache_creation_input_tokens": 31000,
                "cache_read_input_tokens": 900000,
            },
        }
    )
    assert full == {
        "duration_s": 90,
        "cost_usd": 0.42,
        "total_input_tokens": 931118,
        "cache_read_tokens": 900000,
        "output_tokens": 4200,
    }
    assert seams._cost({"type": "result"}) == {}
    assert seams._cost(None) == {}


def test_cost_extraction_tolerates_a_usage_dict_missing_some_fields():
    partial = seams._cost({"usage": {"output_tokens": 5}})
    assert partial == {"output_tokens": 5}


@needs_git
def test_run_maintainer_streams_progress_reports_cost_and_the_model(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    script = tmp_path / "maintainer.sh"
    script.write_text(
        "#!/bin/sh\ncat > /dev/null\n"
        'echo \'{"type":"system","subtype":"init","model":"fixture-model-9"}\'\n'
        'echo \'{"type":"result","subtype":"success","result":"done",'
        '"duration_ms":2000,"total_cost_usd":0.01,'
        '"usage":{"input_tokens":10,"output_tokens":5}}\'\n'
    )
    script.chmod(0o755)
    code, product, cost = seams.run_maintainer(str(script), tmp_path, wiki, "task", "label")
    assert code == 0
    assert product == "done"
    assert cost == {
        "duration_s": 2,
        "cost_usd": 0.01,
        "total_input_tokens": 10,
        "output_tokens": 5,
        "model": "fixture-model-9",
    }


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


# --- wikimap: SPEC-wiki-009 ------------------------------------------------------


def test_render_is_empty_for_a_wiki_with_no_linkable_page(tmp_path):
    wiki = wiki_with(tmp_path)
    assert wikimap.render(wiki) == ""


def test_render_lists_every_non_pinned_page_with_its_heading(tmp_path):
    wiki = wiki_with(
        tmp_path,
        sources__a="# The A Video\n\nbody",
        notes__b="# The B Note\n\nbody",
    )
    rendered = wikimap.render(wiki)
    assert "sources/a.md" in rendered and "The A Video" in rendered
    assert "notes/b.md" in rendered and "The B Note" in rendered
    assert layout.BRIEF not in rendered and layout.INDEX not in rendered


def test_render_bounds_a_line_and_never_inlines_the_body(tmp_path):
    tell = "distinctive-marker-that-must-not-leak"
    body = (tell + " padding " * 40) * 5
    wiki = wiki_with(tmp_path, notes__long=f"# Short heading\n\n{body}")
    rendered = wikimap.render(wiki)
    assert tell not in rendered
    lines = [line for line in rendered.splitlines() if "notes/long.md" in line]
    assert len(lines) == 1 and len(lines[0]) <= wikimap.LINE_BUDGET


# --- repo: the lock, and SPEC-wiki-012's wait ------------------------------------


@needs_git
def _bare_wiki(tmp_path) -> Path:
    wiki = tmp_path / "wiki"
    repo.ready(wiki)
    return wiki


@needs_git
def test_held_refuses_at_once_by_default_when_the_lock_is_taken(tmp_path):
    wiki = _bare_wiki(tmp_path)
    with repo.held(wiki):
        with pytest.raises(Busy):
            with repo.held(wiki):
                pass  # never reached


@needs_git
def test_held_with_wait_blocks_until_the_holder_releases_then_proceeds(tmp_path):
    wiki = _bare_wiki(tmp_path)
    entered = threading.Event()
    released = threading.Event()
    waiter_got_in = threading.Event()

    def hold_first():
        with repo.held(wiki):
            entered.set()
            released.wait(timeout=5)

    holder = threading.Thread(target=hold_first)
    holder.start()
    entered.wait(timeout=5)

    def wait_for_it():
        with repo.held(wiki, wait=True):
            waiter_got_in.set()

    waiter = threading.Thread(target=wait_for_it)
    waiter.start()
    time.sleep(0.3)
    assert not waiter_got_in.is_set(), "the waiter must not proceed while the lock is held"

    released.set()
    holder.join(timeout=5)
    waiter.join(timeout=5)
    assert waiter_got_in.is_set(), "the waiter must proceed once the holder releases the lock"


@needs_git
def test_held_with_wait_on_a_free_lock_proceeds_immediately(tmp_path):
    wiki = _bare_wiki(tmp_path)
    with repo.held(wiki, wait=True):
        pass  # no contention, no announcement expected — nothing to assert but that it returns
