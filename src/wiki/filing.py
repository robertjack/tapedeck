"""The verbs that write: one filing, and the two sweeps built out of it.

`file <id>` is the unit of work, and both sweeps are loops around that operation
rather than second implementations of it (SPEC-wiki-003, SPEC-wiki-005) — the
same maintainer seam, the same whole-wiki gate, the same `user edits` pre-run
commit, one commit per accepted filing and one rollback per rejected one. A sweep
that verified less than the single verb would be a way to get unreviewed prose
into the wiki by asking for more of it at once, and per-video commits are what
keep the history legible after a sweep of forty.

One video's failure never stops a sweep. The alternative is a sweep whose result
depends on where in the alphabet the first bad video sat: the user re-runs it,
pays for everything again, and stops at the next bad one.

`rebuild` is the same sweep from zero, and it is the only verb here that asks
before it acts. It destroys hand-written prose that nothing can re-derive, so
consent is the specification: without `--yes` it executes nothing at all and only
says what it would do. Git is what makes saying yes survivable — the wiki it
replaces is one `git show` away for as long as the repository lasts.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import ingest

from . import Failure, Usage, gate, seams
from .layout import (
    BRIEF,
    INDEX,
    LOG,
    NOTES,
    SOURCES,
    append_entry,
    archive_page,
    bytes_of,
    eligible,
    entry_of,
    source_page,
    today,
    wiki_dir,
)
from .repo import Repo

RESET = "wiki rebuild: reset"


def note(message: str) -> None:
    print(message, file=sys.stderr)


# --- one video ---


def file_one(home: Path, wiki: Path, repo: Repo, video_id: str, command: str) -> None:
    """The operation every wiki filing is: the user's pending work committed, the
    maintainer run, the whole wiki judged, and then either one commit or a
    rollback to exactly where this began."""
    repo.commit_pending()
    before = repo.head()
    brief_before = bytes_of(wiki / BRIEF)
    log_before = bytes_of(wiki / LOG) or b""

    try:
        seams.run_maintainer(
            command, home, wiki, video_id, archive_page(home, video_id), today()
        )
        problems = gate.violations(home, wiki, video_id, brief_before, log_before)
    except Failure as exc:
        repo.restore(before)
        raise Failure(f"{video_id}: {exc}") from exc

    if problems:
        repo.restore(before)
        raise Failure(
            f"{video_id}: the wiki this filing produced was not accepted:\n  "
            + "\n  ".join(problems)
        )
    repo.commit(f"wiki file {video_id}")


def file_verb(home: Path, video_id: str) -> int:
    """`file <id>`: the cheap questions first, so nothing probabilistic runs until
    every one of them is settled."""
    if not ingest.VIDEO_ID.fullmatch(video_id):
        raise Usage(f"{video_id!r} is not a video id — ids are 11 characters wide")
    entry = entry_of(home, video_id)
    if not entry.is_dir():
        raise Usage(f"no video {video_id} in the library — `tapedeck list` has what is")
    if not ingest.has_video(entry):
        raise Usage(
            f"{video_id} has no video file in the library — its media was reclaimed, "
            f"and `tapedeck add {video_id}` fetches it back"
        )
    page = archive_page(home, video_id)
    if not page.is_file():
        raise Failure(
            f"{video_id}: no archive page at {page} — the maintainer files from that "
            f"page, so `tapedeck add {video_id}` has to render it first"
        )

    wiki = wiki_dir(home)
    if source_page(wiki, video_id).is_file():
        note(f"{video_id} is already filed — nothing to do")
        return 0

    command = seams.maintainer_command(home)
    repo = Repo(wiki)
    repo.ensure()
    file_one(home, wiki, repo, video_id, command)
    return 0


# --- the whole library ---


def sweep(
    home: Path,
    wiki: Path,
    repo: Repo,
    command: str,
    pending: list[str],
    already: int,
    skipped: int,
) -> int:
    """File each unfiled video in turn, survive the ones that fail, and account
    for every outcome in one line — the count is what the user came back to read."""
    filed = failed = 0
    for position, video_id in enumerate(pending, start=1):
        note(f"[{position}/{len(pending)}] filing {video_id}")
        try:
            file_one(home, wiki, repo, video_id, command)
            filed += 1
        except Failure as exc:
            failed += 1
            note(f"error: {exc}")
    print(f"filed {filed}, already filed {already}, skipped {skipped}, failed {failed}")
    return 1 if failed else 0


def unfiled(wiki: Path, ids: list[str]) -> list[str]:
    """Eligible and carrying no source page. There is no queue and no manifest:
    the filed-state marker is the page's existence, so the question "what is
    left" is answered by the filesystem and cannot disagree with itself."""
    return [video_id for video_id in ids if not source_page(wiki, video_id).is_file()]


def sync(home: Path, dry_run: bool) -> int:
    ids, skipped = eligible(home, note)
    wiki = wiki_dir(home)
    pending = unfiled(wiki, ids)
    if dry_run:
        # A rehearsal changes nothing whatsoever, and creating a repository is
        # not nothing: a user asking what a sweep would do has not asked for one.
        for video_id in pending:
            print(video_id)
        return 0
    command = seams.maintainer_command(home)
    repo = Repo(wiki)
    repo.ensure()
    return sweep(home, wiki, repo, command, pending, len(ids) - len(pending), skipped)


# --- from zero ---


def _clearable(wiki: Path) -> dict[str, list[Path]]:
    """Every file the reset would remove, by the directory it sits in."""
    return {
        name: sorted(path for path in (wiki / name).rglob("*") if path.is_file())
        for name in (SOURCES, NOTES)
    }


def _preview(wiki: Path, ids: list[str]) -> None:
    """What `--yes` would consent to, said before any of it has happened."""
    clearable = _clearable(wiki)
    print(f"wiki: {wiki}")
    print(
        f"the reset would remove {len(clearable[SOURCES])} file(s) under {SOURCES}/ "
        f"and {len(clearable[NOTES])} under {NOTES}/, and empty {INDEX}. "
        f"{BRIEF} and {LOG} survive it untouched."
    )
    print(f"it would then refile {len(ids)} video(s), in this order:")
    for video_id in ids:
        print(f"  {video_id}")
    print(
        "nothing has happened yet — re-run with --yes to do it. The wiki as it "
        "stands stays in this repository's history and can be read back out of it "
        "long after."
    )


def _reset(repo: Repo, wiki: Path, cleared: int) -> None:
    """One commit, because the state being recorded is "the old wiki, entire" and
    the user restoring it should have exactly one thing to name."""
    for name in (SOURCES, NOTES):
        directory = wiki / name
        if directory.is_dir():
            shutil.rmtree(directory)
    repo.shape()
    (wiki / INDEX).write_text("", encoding="utf-8")
    append_entry(
        wiki / LOG,
        "rebuild",
        f"the wiki was emptied and refiled ({cleared} file(s) cleared)",
        "Everything under sources/ and notes/ was removed and the catalog reset; "
        "the filings below are the library read again from the start.",
    )
    repo.commit(RESET)


def rebuild(home: Path, yes: bool) -> int:
    wiki = wiki_dir(home)
    if not wiki.is_dir():
        # `file` and `sync` scaffold because filing into a wiki is what they are
        # for; rebuild is a verb about an existing wiki's contents.
        raise Usage(
            f"no wiki at {wiki} — `python -m wiki file <id>` or `python -m wiki sync` "
            f"is what brings one into being"
        )
    ids, skipped = eligible(home, note)
    if not yes:
        _preview(wiki, ids)
        return 0

    # Before anything is destroyed: a reset whose refill cannot run is the one
    # outcome nobody wants.
    command = seams.maintainer_command(home)
    cleared = sum(len(found) for found in _clearable(wiki).values())
    repo = Repo(wiki)
    # A wiki that exists is always a repository of its own (the layout contract),
    # and every step below is a git operation: one that ran against a directory
    # some *other* repository happened to contain would commit and clean there.
    # This repairs that invariant and cannot create a wiki — a missing one exited
    # two checks ago.
    repo.ensure()
    repo.commit_pending()
    _reset(repo, wiki, cleared)
    pending = unfiled(wiki, ids)
    return sweep(home, wiki, repo, command, pending, len(ids) - len(pending), skipped)
