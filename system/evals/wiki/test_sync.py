"""Durable evals: the `sync` sweep (SPEC-wiki-003).

Boundary: `python -m wiki sync [--dry-run]`; maintainer seam faked through
config.toml, ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

`file` is one video; `sync` is the library. Everything expensive about it is
already pinned by SPEC-wiki-002 and is deliberately not re-decided here — each
unfiled video goes through the same operation, the same gate, the same per-video
commit and the same per-video rollback. What this suite pins is the sweep around
that: which entries it selects, the order it works in, and what it does when one
video's filing fails.

The order matters more here than anywhere else in tapedeck. The wiki is
path-dependent state (SPEC-wiki-001) — a maintainer reading the wiki as it stands
writes a different note than one reading it empty — so the order videos are filed
in is part of the artifact, not an implementation detail. Chronological is the
order the material appeared, and it is the only order a second sync, on another
machine, a year later, would reproduce.

Eligibility is other components' vocabulary (LESSON-0003): a well-formed id and a
video that is present are ingest's rules, and the page the maintainer reads is
archive's. The sweep consumes all three and skips whatever fails them, exactly as
the retranscribe sweep does (SPEC-cli-004) — a library keeps entries no sweep can
ever satisfy, and a sweep that fails on them can never converge.
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
    wiki_sync,
)

FOREIGN = "reading-notes"     # a directory of the user's own under library/
MEDIALESS = "tie-alpha-1"     # `rm --media-only` kept the knowledge, dropped the video
PAGELESS = "tie-zebra-2"      # in the library, never rendered by archive
ALREADY = "middle00002"       # filed by hand before the sweep ever runs
BROKEN = "middle00002"        # the one video whose filing the gate rejects


def unfilable_library(home):
    """The library as it actually ages: two videos the sweep can file, one whose
    media was reclaimed, one archive never rendered, and one directory that is
    not a video at all."""
    unfiled_library(home, pages=[v for v in SWEEP_ORDER if v != PAGELESS])
    for path in (home / "library" / MEDIALESS).glob("video.*"):
        path.unlink()
    (home / "library" / FOREIGN).mkdir()
    (home / "library" / FOREIGN / "scratch.md").write_text("mine, not tapedeck's\n")
    return [v for v in SWEEP_ORDER if v not in (MEDIALESS, PAGELESS)]


# --- the sweep ---------------------------------------------------------------


def test_an_unfiled_library_is_filed_in_upload_date_order(home, monkeypatch):
    """The wiki accumulates in the order the material appeared, so the fixture
    library's chronology disagrees with its alphabet and with the order its
    directories were created."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_EACH_ID)

    r = wiki_sync(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    assert maintainer_ids(home) == SWEEP_ORDER, (
        f"the maintainer met the library in the wrong order — a wiki written "
        f"against a different past is a different wiki: {maintainer_ids(home)}"
    )

    wiki = home / "wiki"
    for vid in SWEEP_ORDER:
        assert (wiki / "sources" / f"{vid}.md").is_file(), f"{vid} was not filed"
    assert [subject for op, subject in log_entries(wiki) if op == "file"] == SWEEP_ORDER, (
        f"the chronology disagrees with the order the sweep worked in: "
        f"{log_entries(wiki)}"
    )

    filings = [s for s in subjects(wiki) if s.startswith("wiki file")]
    assert [s.split()[-1] for s in filings] == list(reversed(SWEEP_ORDER)), (
        f"each video is its own commit, so any one filing can be read or reverted "
        f"on its own: {subjects(wiki)}"
    )
    assert not git(wiki, "status", "--porcelain").stdout.strip()
    assert re.search(r"\b4\b", summary_line(r)), summary_line(r)


def test_videos_already_filed_are_skipped_without_running_the_maintainer(home, monkeypatch):
    """The sources page is the filed-state marker and there is no other record to
    consult. A sweep that re-files what is already filed spends an agent
    invocation per video to arrive back where it started."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_EACH_ID)
    assert wiki_file(home, ALREADY).returncode == 0
    (home / "maintainer-ids").unlink()

    wiki = home / "wiki"
    already = (wiki / "sources" / f"{ALREADY}.md").read_bytes()

    r = wiki_sync(home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert maintainer_ids(home) == [v for v in SWEEP_ORDER if v != ALREADY], (
        f"the sweep paid for a video that was already filed: {maintainer_ids(home)}"
    )
    assert (wiki / "sources" / f"{ALREADY}.md").read_bytes() == already, (
        "the page of an already-filed video was rewritten"
    )
    assert len([e for e in log_entries(wiki) if e[0] == "file"]) == 4, (
        "one entry per filing, and the first filing's entry is not repeated"
    )


def test_entries_the_sweep_cannot_file_are_skipped_and_left_alone(home, monkeypatch):
    """Foreign directories, entries whose media was reclaimed, and videos archive
    has not rendered are all outside the sweep's reach. None of them is a failure:
    they are permanent residents of a real library, and a sweep that fails on them
    fails forever."""
    filable = unfilable_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_EACH_ID)

    r = wiki_sync(home)
    assert r.returncode == 0, (
        f"an entry the sweep cannot file is not a failed sweep:\n{r.stderr}"
    )
    assert maintainer_ids(home) == filable, maintainer_ids(home)
    for name in (FOREIGN, MEDIALESS, PAGELESS):
        assert name in r.stderr, (
            f"a skipped entry the user cannot see is an entry they will never fix: "
            f"{r.stderr!r}"
        )

    assert (home / "library" / FOREIGN / "scratch.md").is_file(), "the user's own files"
    stripped = home / "library" / MEDIALESS
    assert (stripped / "meta.json").is_file() and (stripped / "transcript.json").is_file()
    wiki = home / "wiki"
    for name in (MEDIALESS, PAGELESS):
        assert not (wiki / "sources" / f"{name}.md").exists(), (
            f"{name} is not eligible and must not have been filed"
        )


def test_one_rejected_filing_does_not_stop_the_sweep(home, monkeypatch):
    """A maintainer is probabilistic and one video in a hundred will produce a
    wiki the gate refuses. Stopping there would make a long sweep a lottery: the
    user re-runs it, pays for everything again, and stops at the next bad one."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, links_to_nothing_for(BROKEN))

    r = wiki_sync(home)
    assert r.returncode == 1, (
        f"a sweep that could not file everything did not succeed:\n{r.stdout}\n{r.stderr}"
    )
    assert maintainer_ids(home) == SWEEP_ORDER, (
        f"the sweep stopped at the video that failed: {maintainer_ids(home)}"
    )

    wiki = home / "wiki"
    assert not (wiki / "sources" / f"{BROKEN}.md").exists(), (
        "the rejected filing was rolled back, so its page is not there"
    )
    for vid in SWEEP_ORDER:
        if vid != BROKEN:
            assert (wiki / "sources" / f"{vid}.md").is_file(), f"{vid} was not filed"

    assert BROKEN in r.stderr, f"the failure names the video it happened to: {r.stderr!r}"
    assert "nonexistent-page" in r.stderr, (
        f"and carries the gate's own violation, so the user can act on it: {r.stderr!r}"
    )
    line = summary_line(r)
    assert re.search(r"\b3\b", line) and re.search(r"\b1\b", line), line
    assert len([s for s in subjects(wiki) if s.startswith("wiki file")]) == 3
    assert not git(wiki, "status", "--porcelain").stdout.strip()


def test_a_fully_filed_library_is_a_no_op(home, monkeypatch):
    """Convergence is the point of the verb: once everything filable is filed the
    next sweep costs nothing, so the user can re-run it after every `add` without
    keeping track of where the last one stopped."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_EACH_ID)
    assert wiki_sync(home).returncode == 0

    wiki = home / "wiki"
    before, history = snapshot(wiki), subjects(wiki)
    set_maintainer(home, MUST_NOT_RUN)

    again = wiki_sync(home)
    assert again.returncode == 0, f"a no-op is not an error:\n{again.stderr}"
    assert not (home / "maintainer-ran").exists(), "the maintainer was invoked anyway"
    assert snapshot(wiki) == before and subjects(wiki) == history

    rehearsal = wiki_sync(home, "--dry-run")
    assert rehearsal.returncode == 0 and rehearsal.stdout.split() == [], (
        f"with nothing left to file the rehearsal promises nothing: {rehearsal.stdout!r}"
    )


# --- the rehearsal -----------------------------------------------------------


def test_dry_run_promises_exactly_what_the_sweep_would_do(home):
    """The rehearsal exists to be trusted before an expensive run: it lists what
    the sweep would file, in the order it would file them, and does nothing. No
    maintainer is configured here at all — a run that spends nothing needs no
    agent to spend it on."""
    filable = unfilable_library(home)

    r = wiki_sync(home, "--dry-run")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert r.stdout.split() == filable, (
        f"stdout is the list of ids the sweep would file, one per line, in sweep "
        f"order and nothing else: {r.stdout!r}"
    )
    for name in (FOREIGN, MEDIALESS, PAGELESS):
        assert name in r.stderr, (
            f"the rehearsal reports the same skips as the sweep: {r.stderr!r}"
        )
    assert not (home / "wiki").exists(), (
        "a rehearsal that scaffolds a wiki has already changed the library it "
        "promised to leave alone"
    )


def test_a_sweep_with_no_maintainer_configured_exits_2(home, monkeypatch):
    """The seam is the sweep's precondition, not each filing's: discovering it is
    missing on the first video, after walking the library, is the same usage error
    `file` reports and it costs the user the same nothing."""
    unfiled_library(home)
    set_ask(monkeypatch, home)
    before = (home / "config.toml").read_text()

    r = wiki_sync(home)
    assert r.returncode == 2, f"an unconfigured seam is a usage error:\n{r.stderr}"
    assert "maintainer_command" in r.stderr, (
        f"the message names the key the user has to set: {r.stderr!r}"
    )
    assert (home / "config.toml").read_text() == before, (
        "wiki wrote config.toml, which is cli's file to scaffold"
    )
