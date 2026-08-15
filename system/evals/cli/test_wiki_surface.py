"""Durable evals: the `wiki` verb group on the executable (SPEC-cli-009).

Boundary: the `tapedeck` executable, library via $TAPEDECK_HOME. The wiki
component underneath is the real one — what is faked here is what is faked
everywhere, and only at the published seams: the maintainer through
`[wiki].maintainer_command` in config.toml, and ask through the `$TAPEDECK_ASK_CMD`
override the harness documents for every component boundary.

`wiki` is a group the cli hands over whole. That is the claim this suite exists to
hold: the ids a rehearsal prints, the JSON a lint emits and the exit code a
rejected filing carries all arrive at the user unaltered, because the cli routes
and adds nothing. Behavior lives in SPEC-wiki-001..005 and is pinned by
system/evals/wiki/; what is pinned here is that the executable is a door and not a
second opinion. The rest of the round's surface — the [wiki] scaffold, doctor's
row, and the note `rm` owes a filed video — is the cli's own and is pinned here
because no other component can.

conftest.set_maintainer writes config.toml wholesale, so every config in this file
is hand-written: a test that needs both a resolvable pipeline and a maintainer
needs them in one file. The maintainer fakes follow system/evals/wiki/wikilib.py —
one honest body, plus a single line that breaks one rule where a test wants a
refusal.
"""

import json
import re
import shutil
import tomllib

import pytest

from conftest import (
    CHAPTERED_META,
    PLAIN_META,
    add_video,
    run_cli,
    write_archive_page,
)

FILED = CHAPTERED_META["id"]  # uploaded 2026-01-15 — first in the sweep's order
NEXT = PLAIN_META["id"]       # uploaded 2026-02-02 — second

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]

# SPEC-wiki-002's published default, verbatim, and the reason it is written out
# here rather than read from anywhere: the scaffold's job is to carry exactly this
# line to a fresh install, and a test that derived it from the same source the
# scaffold derives it from would agree with any drift.
DEFAULT_MAINTAINER_COMMAND = (
    'claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"'
)

# SPEC-cli-007's fixed order, with the wiki seam in the position this round pins:
# after the other optional seams, before the tools the derivation needs.
DOCTOR_CHECKS = (
    "ingest.fetcher_command",
    "ingest.lister_command",
    "transcribe.transcriber_command",
    "ask.librarian_command",
    "ask.answerer_command",
    "wiki.maintainer_command",
    "ffmpeg",
    "home",
    "fts5",
    "platform",
)

# SPEC-wiki-004's checks, in its order — quoted here only to prove the report the
# component printed is the report the user received.
LINT_CHECKS = ("wikilinks", "citations", "index", "log", "sources", "filed", "unfiled", "orphans")

MISSING = "tapedeck-no-such-tool-2f9c1a"


# --- the seams ----------------------------------------------------------------

ASK_VERIFIES = """#!/bin/sh
cat > /dev/null
"""

SH = """#!/bin/sh
cat > /dev/null
"""

# The least a maintainer can do and still be accepted: the page whose existence is
# the filed marker, citing the video it is about, and the catalog line for it.
FILES_THE_VIDEO = """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Filed from [the moment it matters](https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID&t=95s).
MD
grep -q "sources/$TAPEDECK_VIDEO_ID.md" index.md ||
  echo "- [$TAPEDECK_VIDEO_ID](sources/$TAPEDECK_VIDEO_ID.md)" >> index.md
"""

LOGS_IT = """
{ echo; echo "## [$(date +%Y-%m-%d)] file | $TAPEDECK_VIDEO_ID"; echo;
  echo "Filed the video."; } >> log.md
"""

GOOD = SH + FILES_THE_VIDEO + LOGS_IT

LINKS_TO_NOTHING = GOOD + """
echo "Compare with [[nonexistent-page]]." >> "sources/$TAPEDECK_VIDEO_ID.md"
"""

MUST_NOT_RUN = """#!/bin/sh
touch "$TAPEDECK_HOME/maintainer-ran"
echo "the maintainer was invoked and should not have been" >&2
exit 9
"""


def set_ask(monkeypatch, home, script_body=ASK_VERIFIES):
    """Point the wiki's citation check at a fake ask, the way system/evals/wiki
    does: exit 0 means every deep link in the text on stdin verified. Which
    citations are true is ask's question and is settled in ask's own suite; here
    it only has to be settled the same way every time."""
    script = home / "fake-ask.sh"
    script.write_text(script_body)
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")


def fake_maintainer(home, script_body):
    """A maintainer fake on disk; returns the command that runs it."""
    script = home / "maintainer.sh"
    script.write_text(script_body)
    return f"sh {script}"


def write_config(
    home,
    *,
    maintainer=None,
    auto=None,
    fetcher="sh -c :",
    lister="sh -c :",
    transcriber="sh -c :",
):
    """A config.toml written whole. The seams that `add` needs are pointed at a
    command that resolves and does nothing, so doctor has nothing else to
    complain about; `maintainer` is a command string (fake_maintainer makes one
    from a script body) and `None` leaves the key — or the whole `[wiki]` table —
    out of the file, which is how an unconfigured install looks."""
    lines = [
        "[ingest]",
        f'fetcher_command = "{fetcher}"',
        f'lister_command = "{lister}"',
        "",
        "[transcribe]",
        f'transcriber_command = "{transcriber}"',
        'model = "fixture/whisper-0"',
    ]
    if maintainer is not None or auto is not None:
        lines += ["", "[wiki]"]
        if maintainer is not None:
            lines.append(f'maintainer_command = "{maintainer}"')
        if auto is not None:
            lines.append(f"auto = {str(auto).lower()}")
    (home / "config.toml").write_text("\n".join(lines) + "\n")


# --- fixture state ------------------------------------------------------------


def stocked(home):
    """Two videos archive has rendered — the library a sweep can work on."""
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    add_video(home, PLAIN_META, [{"start": 2.0, "end": 6.0, "text": "Sourdough."}])
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)


def filed_wiki(home, monkeypatch, video_id=FILED):
    """A wiki with one video filed, built through the executable itself, since
    that is the surface under test. Returns the wiki directory."""
    stocked(home)
    set_ask(monkeypatch, home)
    write_config(home, maintainer=fake_maintainer(home, GOOD))
    r = run_cli(["wiki", "file", video_id], home)
    assert r.returncode == 0, f"the fixture wiki must file cleanly:\n{r.stdout}\n{r.stderr}"
    return home / "wiki"


def snapshot(wiki):
    """Every byte of the wiki but its git internals — equality with a later
    snapshot is what "changed nothing" means."""
    return {
        str(p.relative_to(wiki)): p.read_bytes()
        for p in sorted(wiki.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(wiki).parts
    }


def doctor(home):
    """Run `tapedeck doctor --json` and return (result, {check: row})."""
    r = run_cli(["doctor", "--json"], home)
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        raise AssertionError(
            f"`doctor --json` did not emit JSON (exit {r.returncode}):\n"
            f"stdout={r.stdout!r}\nstderr={r.stderr!r}"
        ) from exc
    return r, {row["check"]: row for row in rows}


# --- the group is handed over whole -------------------------------------------


def test_sync_dry_run_prints_the_ids_the_component_would_file(home):
    """The rehearsal a user reads before an expensive sweep, arriving through the
    executable exactly as the component printed it: the ids, in the sweep's order,
    on stdout, and nothing added to them. No maintainer is configured — a run that
    spends nothing needs no agent to spend it on."""
    stocked(home)

    r = run_cli(["wiki", "sync", "--dry-run"], home)
    assert r.stdout.split() == [FILED, NEXT], (
        f"stdout is the component's list of ids, one per line, in its own sweep "
        f"order — the cli neither reorders it nor decorates it: {r.stdout!r}"
    )
    assert "invalid choice" not in r.stderr, (
        f"`wiki` must be a verb the cli routes, not one argparse rejects: {r.stderr!r}"
    )
    assert not (home / "wiki").exists(), (
        "a rehearsal that scaffolds a wiki has already done something"
    )


def test_file_files_the_video_through_the_executable(home, monkeypatch):
    """The whole point of the verb: after it, the library has a wiki page for that
    video, and the page is the filed-state marker itself (contracts/wiki-layout.md)."""
    stocked(home)
    set_ask(monkeypatch, home)
    write_config(home, maintainer=fake_maintainer(home, GOOD))

    r = run_cli(["wiki", "file", FILED], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    wiki = home / "wiki"
    assert (wiki / "sources" / f"{FILED}.md").is_file(), (
        f"the video was not filed:\n{r.stdout}\n{r.stderr}"
    )
    assert f"sources/{FILED}.md" in (wiki / "index.md").read_text(), (
        "the filed page is missing from the catalog, so the component's own gate "
        "cannot have run"
    )


def test_a_rejected_filing_carries_the_components_exit_code_and_words(home, monkeypatch):
    """A maintainer that breaks one rule is refused by the gate, and what the user
    gets is the component's answer: exit 1, the violation on stderr, and a wiki
    with nothing left behind in it. Exit 1 is the load-bearing part — a cli that
    translated a failed operation into a usage error, or swallowed it into 0,
    would be answering for a component it only routes to."""
    wiki = filed_wiki(home, monkeypatch)
    write_config(home, maintainer=fake_maintainer(home, LINKS_TO_NOTHING))

    r = run_cli(["wiki", "file", NEXT], home)
    assert r.returncode == 1, (
        f"the component's exit code is the user's, and a refused filing is 1: "
        f"exit {r.returncode}\n{r.stdout}\n{r.stderr}"
    )
    assert "nonexistent-page" in r.stderr, (
        f"the gate's own violation reaches the user unedited: {r.stderr!r}"
    )
    assert not (wiki / "sources" / f"{NEXT}.md").exists(), (
        "the rejected filing was rolled back, so its page is not there"
    )


def test_lint_json_arrives_as_the_component_wrote_it(home, monkeypatch):
    """`--json` is the subcommand's flag, not the cli's: it is passed through
    untouched and the report on stdout is machine-readable at the far end."""
    filed_wiki(home, monkeypatch)

    r = run_cli(["wiki", "lint", "--json"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        raise AssertionError(
            f"`tapedeck wiki lint --json` did not emit the component's JSON:\n"
            f"stdout={r.stdout!r}\nstderr={r.stderr!r}"
        ) from exc
    assert [row["check"] for row in rows] == list(LINT_CHECKS), (
        f"the report the component printed is not the report the user received: {rows}"
    )


def test_lint_without_a_wiki_exits_2_naming_the_path_it_looked_for(home):
    """The component's refusal, verbatim: which wiki was resolved is the whole
    question a surprising $TAPEDECK_HOME raises, so the answer has to survive the
    trip out. Exit 2 alone proves nothing here — argparse says 2 for a verb it has
    never heard of — so the path is what this test is actually asking for."""
    r = run_cli(["wiki", "lint"], home)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert str(home / "wiki") in r.stderr, (
        f"exit 2 must mean 'there is no wiki to check', named by its resolved path, "
        f"and not 'wiki is not a recognized verb': {r.stderr!r}"
    )
    assert "invalid choice" not in r.stderr, r.stderr
    assert not (home / "wiki").exists(), "lint must not create the wiki it was asked to check"


def test_rebuild_without_yes_previews_and_changes_nothing(home, monkeypatch):
    """Consent survives the routing. Without `--yes` the user reads what would
    happen and none of it has happened: no maintainer invoked, not one byte of the
    wiki different."""
    wiki = filed_wiki(home, monkeypatch)
    write_config(home, maintainer=fake_maintainer(home, MUST_NOT_RUN))
    before = snapshot(wiki)

    r = run_cli(["wiki", "rebuild"], home)
    assert r.returncode == 0, f"a preview that changed nothing did not fail:\n{r.stderr}"
    assert str(wiki) in r.stdout, (
        f"the wiki about to be destroyed is named by its resolved path: {r.stdout!r}"
    )
    assert FILED in r.stdout, (
        f"and so is what it would refile, which is the half the user is agreeing to: "
        f"{r.stdout!r}"
    )
    assert not (home / "maintainer-ran").exists(), "the maintainer was invoked anyway"
    assert snapshot(wiki) == before, "the preview wrote to the wiki"


# --- the cli's own surface ----------------------------------------------------


def test_the_first_run_config_carries_the_wiki_section(tmp_path):
    """A fresh install can file without editing anything: the scaffold ships the
    published maintainer default and auto-filing already on, in the same commented
    style as the seams beside it. The default is compared whole — a command that
    grants the agent one more tool than SPEC-wiki-002 published is a different
    default, not a formatting difference."""
    home = tmp_path / "fresh" / "deck"  # does not exist yet
    assert run_cli(["list"], home).returncode == 0

    raw = (home / "config.toml").read_text()
    assert "[wiki]" in raw, f"first-run config.toml has no [wiki] section:\n{raw}"
    config = tomllib.loads(raw)
    assert config["wiki"]["maintainer_command"] == DEFAULT_MAINTAINER_COMMAND, (
        f"the scaffolded seam is not SPEC-wiki-002's published default: "
        f"{config['wiki'].get('maintainer_command')!r}"
    )
    assert config["wiki"]["auto"] is True, (
        f"auto-filing ships on, written out rather than left to be inferred: "
        f"{config['wiki'].get('auto')!r}"
    )


def test_doctor_reports_the_wiki_seam_in_the_pinned_position(home):
    """One more row in doctor's fixed order, in the place SPEC-cli-009 puts it."""
    write_config(home, maintainer=f"{MISSING}-agent -p")
    _, rows = doctor(home)

    assert list(rows) == list(DOCTOR_CHECKS), (
        f"the wiki seam belongs between the ask seams and ffmpeg, and every check "
        f"is still reported: {list(rows)}"
    )
    row = rows["wiki.maintainer_command"]
    assert row["status"] == "optional", (
        f"an agent that cannot be resolved costs the wiki, not the library: {row!r}"
    )
    detail = row["detail"].lower()
    assert "wiki" in detail and "add" in detail, (
        f"the optional reason must say what its absence costs — the wiki verbs and "
        f"the filing `add` would have done: {row['detail']!r}"
    )


def test_the_wiki_seam_never_decides_doctors_exit_code(home):
    """Absent, unresolvable or fine, the answer to `is this install healthy` is the
    same — exactly as the [ask] seams behave (SPEC-cli-007)."""
    if shutil.which("ffmpeg") is None:  # a real gap on this host, not doctor's fault
        pytest.skip("ffmpeg is genuinely absent here, so exit 1 would be the right answer")

    write_config(home, maintainer="sh -c :")
    healthy, rows = doctor(home)
    assert rows["wiki.maintainer_command"]["status"] in {"pass", "optional"}, rows
    assert healthy.returncode == 0, (
        "a resolvable maintainer is not a reason to fail: "
        f"{sorted(n for n, r in rows.items() if r['status'] == 'fail')}"
    )

    for maintainer in (None, f"{MISSING}-agent -p"):
        write_config(home, maintainer=maintainer)
        r, rows = doctor(home)
        assert rows["wiki.maintainer_command"]["status"] == "optional", rows
        assert r.returncode == healthy.returncode, (
            f"a maintainer of {maintainer!r} moved the exit code from "
            f"{healthy.returncode} to {r.returncode}; an optional seam decides nothing"
        )


def test_help_wiki_shows_the_group_and_a_worked_example(home):
    """The group is reachable from `help` like every other verb (SPEC-cli-005),
    and it teaches by example rather than by listing flags."""
    r = run_cli(["help", "wiki"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "usage:" in r.stdout
    assert "tapedeck wiki" in r.stdout, "per-verb help includes a worked example"
    for sub in ("file", "sync", "lint", "rebuild"):
        assert re.search(rf"\b{sub}\b", r.stdout), (
            f"the group's help does not name {sub!r}: {r.stdout!r}"
        )
    assert "\x1b" not in r.stdout, "piped output carries no escape sequences"


def test_rm_notes_the_wiki_page_only_on_full_removal(home, monkeypatch):
    """`rm` cannot fix the wiki — the wiki component is its sole writer — so all it
    owes the user is a word about what it just orphaned, and only when it orphaned
    something. Removing an unfiled video says nothing, `--media-only` says nothing
    because keeping the knowledge is the entire point of the flag
    (SPEC-cli-002 + SPEC-wiki-004), and a full removal names the one command that
    will list what is now dangling."""
    wiki = filed_wiki(home, monkeypatch)
    assert run_cli(["reindex"], home).returncode == 0
    page = wiki / "sources" / f"{FILED}.md"

    unfiled = run_cli(["rm", NEXT], home)
    assert unfiled.returncode == 0, unfiled.stderr
    assert "wiki" not in unfiled.stderr.lower(), (
        f"there is no page for this video, so there is nothing to warn about: "
        f"{unfiled.stderr!r}"
    )

    kept = run_cli(["rm", FILED, "--media-only"], home)
    assert kept.returncode == 0, kept.stderr
    assert "wiki" not in kept.stderr.lower(), (
        f"--media-only keeps the knowledge on purpose; a warning here would be "
        f"telling the user off for using the flag as designed: {kept.stderr!r}"
    )

    gone = run_cli(["rm", FILED], home)
    assert gone.returncode == 0, gone.stderr
    assert "wiki lint" in gone.stderr, (
        f"the note names the command that will list the page now left dangling: "
        f"{gone.stderr!r}"
    )
    assert page.is_file(), (
        "the cli deleted a page in the wiki; the wiki component is its sole writer "
        "and the user decides what happens to what they wrote"
    )
