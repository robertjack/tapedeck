"""The operations that write: `file`, `sync`, `rebuild`, `tend`.

All four are one operation with different reasons for running it. Whatever is
pending in the working tree is committed as `user edits`; the maintainer runs; if
it crashes or the gate refuses, the tree goes back to that pre-run commit and the
run exits 1; otherwise everything it wrote is committed under a name that says
what happened. `sync` is a loop around that operation and `rebuild` is the same
loop preceded by a deliberate reset — neither is a second implementation of it,
because a sweep that verified less than the single verb would be a way to get
unreviewed prose into the wiki by asking for more of it at once.

`tend` is the same operation again, with the one rule filing does not need — no
source page may be deleted or renamed away — and, in its default mode, with the
whole result thrown away. That discard is unconditional and is the whole
guarantee: an agent told to be read-only is a hope, and a reset afterwards is a
fact.

One operation holds the wiki at a time (LESSON-0004). The lock is taken once, by
the verb, and held across every filing it performs, so a sweep's commits can never
be interleaved with a neighbour's half-written pages.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import ingest

from . import Failure, Usage, gate, layout, library, repo, seams

FILE_OP = "file"
TEND_OP = "tend"
REBUILD_OP = "rebuild"
RESET_SUBJECT = "wiki rebuild: reset"
TEND_SUBJECT = "wiki tend"

GATE_RULES = """  - CLAUDE.md is byte-identical to how you found it. Never edit the brief.
  - Every [[wikilink]] in every page resolves — case-sensitively, against page
    filenames with .md stripped, anywhere under wiki/.
  - Every deep link in every page names a real video in this library at a
    timestamp inside it. Never cite a moment you have not read.
  - index.md links every page in the wiki except CLAUDE.md, index.md and log.md.
  - log.md still begins with exactly what it said before, and has gained at least
    one entry of the form:
        {entry}
    Append to the chronology. Never reword, reorder, deduplicate or tidy it."""

FILE_TASK = """You are the maintainer of this wiki. Read CLAUDE.md in this directory first:
it is the brief, it is the user's, and where it disagrees with anything below
about *what to write*, it wins.

File one video into the wiki:

    video id      {video_id}
    archive page  {page}
    wiki root     {wiki}   (your working directory)

The archive page is the video's metadata and its transcript, rendered. Read it,
then write sources/{video_id}.md and whatever the brief says this material earns
under notes/ — connecting it to what the wiki already holds is the point of the
exercise, so read the pages it touches before you add another. Link pages to each
other with [[wikilinks]]. Then bring index.md and log.md up to date.

tapedeck checks the result mechanically after you exit, over the whole wiki, and
rejects the operation — discarding everything you wrote — unless all of this holds:

  - sources/{video_id}.md exists and carries at least one deep link to
    {video_id} itself, in the form {link}
{rules}

Nothing above is about the quality of what you write. That is the brief's, and
yours."""

TEND_REPORT_TASK = """You are the maintainer of this wiki. Read CLAUDE.md in this directory first: it
is the brief, and it is what the pages you are about to read were written under.

    wiki root     {wiki}   (your working directory)

Read the whole wiki and report what you found. This run is read-only and the
guarantee is mechanical rather than a request: tapedeck resets and cleans the
working tree after you exit, so nothing you write to a file will survive. Print
your findings as prose on stdout. That is the entire product of this run, it
reaches the user unedited, and nothing parses it.

Look for what a mechanical check cannot see:

  - pages that contradict each other, and claims a later source supersedes
  - concepts the pages keep naming that no page has ever defined
  - cross-links that plainly should exist and do not
  - orphans worth connecting, and pages that have drifted from the brief
  - questions the material raises that nobody has chased

Be specific: name the pages, quote the sentences, and say what you would do about
it. A finding the user cannot act on is not a finding."""

TEND_APPLY_TASK = """You are the maintainer of this wiki. Read CLAUDE.md in this directory first: it
is the brief, it is the user's, and it governs what a page should say.

    wiki root     {wiki}   (your working directory)

Read the whole wiki and improve it. Resolve contradictions, connect pages that
belong linked, write the page a concept has earned by being mentioned everywhere
and defined nowhere, and merge or delete notes that have gone redundant.
Reshaping notes/ is exactly what this run is for: notes may be created,
rewritten, split, merged and deleted freely.

tapedeck checks the result mechanically after you exit, over the whole wiki, and
rejects the operation — discarding everything you did — unless all of this holds:

  - No page under sources/ is deleted or renamed away. A source page's existence
    is what records that its video has been filed; removing one un-files that
    video silently and the next sweep will pay to recreate it. Their prose is
    yours to edit; their paths are not.
{rules}

File no video: a video with no page yet is `tapedeck wiki sync`'s work, not
yours."""


def _rules(op: str) -> str:
    return GATE_RULES.format(entry=f"## [{layout.today()}] {op} | <subject>")


def file_task(wiki: Path, video_id: str, page: Path) -> str:
    return FILE_TASK.format(
        video_id=video_id,
        page=page,
        wiki=wiki,
        link=layout.deep_link_form(video_id),
        rules=_rules(FILE_OP),
    )


def perform(
    home: Path,
    wiki: Path,
    command: str,
    task: str,
    subject: str,
    video_id: str | None = None,
    archive_page: Path | None = None,
    keep_sources: bool = False,
) -> None:
    """One accept-or-roll-back operation, from the pre-run commit to the commit
    or the rollback. The caller holds the lock for exactly this span."""
    pre_run = repo.commit_pending(wiki)
    before = gate.snapshot(wiki)
    code, _ = seams.run_maintainer(command, home, wiki, task, video_id, archive_page)
    if code != 0:
        repo.restore(wiki, pre_run)
        raise Failure(
            f"the maintainer exited {code} — whatever it left half-written has been "
            f"rolled back, and the wiki is where it was"
        )
    problems = gate.verdict(home, wiki, before, video_id=video_id, keep_sources=keep_sources)
    if problems:
        repo.restore(wiki, pre_run)
        raise Failure(*problems)
    repo.commit(wiki, subject)


# --- `file <id>` --------------------------------------------------------------


def file_one(home: Path, wiki: Path, command: str, video_id: str) -> None:
    """The filing itself, once every cheap question is settled and the lock held."""
    page = library.archive_page(home, video_id)
    perform(
        home,
        wiki,
        command,
        file_task(wiki, video_id, page),
        f"wiki {FILE_OP} {video_id}",
        video_id=video_id,
        archive_page=page,
    )


def file_video(home: Path, video_id: str) -> int:
    """`file <id>`: nothing probabilistic runs until the cheap questions are
    settled, and the cheapest of them is whether there is anything to do."""
    if not ingest.VIDEO_ID.fullmatch(video_id):
        raise Usage(f"{video_id!r} is not a video id — ids are 11 characters")
    if not library.holds(home, video_id):
        raise Usage(f"no video {video_id} in the library — `tapedeck list` shows what is")
    page = library.archive_page(home, video_id)
    if not page.is_file():
        raise Failure(
            f"{video_id}: no archive page at {page} — the maintainer files from that "
            f"page, so `tapedeck add {video_id}` has to render it first"
        )

    wiki = layout.wiki_dir(home)
    if layout.filed(wiki, video_id):
        print(
            f"{video_id}: already filed ({layout.name(wiki, layout.source_page(wiki, video_id))})"
            f" — nothing to do",
            file=sys.stderr,
        )
        return 0
    command = seams.maintainer_command(home)
    repo.ready(wiki)
    with repo.held(wiki):
        file_one(home, wiki, command, video_id)
    return 0


# --- sweeping -----------------------------------------------------------------


def sweep(home: Path, wiki: Path, command: str, unfiled: list[str]) -> int:
    """File each of these, one commit and one gate at a time.

    One video's failure never stops the sweep: it is reported, its own operation
    is rolled back by the rules every filing follows, and the next video begins —
    the alternative is a sweep whose result depends on where in the alphabet the
    first bad video sat.
    """
    failed = 0
    for position, video_id in enumerate(unfiled, start=1):
        print(f"[{position}/{len(unfiled)}] filing {video_id}", file=sys.stderr)
        try:
            file_one(home, wiki, command, video_id)
        except Failure as exc:
            failed += 1
            print(f"error: {video_id} was not filed:", file=sys.stderr)
            for line in exc.lines:
                print(f"  {line}", file=sys.stderr)
    return failed


def report(filed: int, already: int, skipped: int, failed: int) -> int:
    """The one line the user came back to read, in words that grep the same on
    every machine."""
    print(
        f"{filed} filed, {already} already filed, {skipped} skipped, {failed} failed"
    )
    return 1 if failed else 0


def selection(home: Path, wiki: Path) -> tuple[list[str], list[str], int]:
    """`(eligible, unfiled, skipped)` — the sweep's whole selection rule.

    Unfiled is eligible and carrying no source page, and there is no queue and no
    last-synced marker behind it: the filesystem answers "what is left", so it
    cannot disagree with itself. A user who deletes a source page has asked for
    that video to be filed again, and the next sweep obliges without being told.
    """
    skips: list[str] = []
    eligible = library.eligible(home, note=skips.append)
    for note in skips:
        print(note, file=sys.stderr)
    return eligible, [vid for vid in eligible if not layout.filed(wiki, vid)], len(skips)


def sync(home: Path, dry_run: bool) -> int:
    wiki = layout.wiki_dir(home)
    eligible, unfiled, skipped = selection(home, wiki)
    if dry_run:
        # A rehearsal changes nothing whatsoever — in particular it does not
        # scaffold a wiki, since creating a repository is not "nothing", and it
        # never reads the maintainer seam, so it is answerable on a machine where
        # no agent is configured at all.
        for video_id in unfiled:
            print(video_id)
        return 0
    command = seams.maintainer_command(home)
    if not unfiled:
        # Idempotence with a price attached: the maintainer costs time and money,
        # so a converged library must not spend one invocation to learn that.
        return report(0, len(eligible), skipped, 0)
    repo.ready(wiki)
    with repo.held(wiki):
        failed = sweep(home, wiki, command, unfiled)
    return report(len(unfiled) - failed, len(eligible) - len(unfiled), skipped, failed)


# --- `rebuild` ----------------------------------------------------------------


def existing(home: Path) -> Path:
    """The wiki a verb about an existing wiki's contents needs. `file` and `sync`
    scaffold because they are about to write a filing into one; asking `rebuild`
    or `tend` for a wiki that was never built is a usage error rather than an
    invitation, and which wiki was resolved is the whole question a surprising
    $TAPEDECK_HOME raises."""
    wiki = layout.wiki_dir(home)
    if not repo.exists(wiki):
        raise Usage(
            f"no wiki at {wiki} — `tapedeck wiki file <id>` or `tapedeck wiki sync` "
            f"is what brings one into being"
        )
    return wiki


def preview(wiki: Path, eligible: list[str]) -> int:
    """What `--yes` would consent to, read before any of it has happened."""
    pages = {tree: len(list((wiki / tree).rglob(f"*{layout.PAGE}"))) for tree in layout.TREES}
    print(f"wiki: {wiki}")
    print(
        "would remove: "
        + ", ".join(f"{count} page(s) under {tree}/" for tree, count in pages.items())
        + f", and empty {layout.INDEX}"
    )
    print(f"would keep: {layout.BRIEF} and {layout.LOG}, and the whole git history")
    if eligible:
        print(f"would refile {len(eligible)}, in this order:")
        for video_id in eligible:
            print(f"  {video_id}")
    else:
        print("would refile nothing — no video in the library is eligible")
    return 0


def reset(wiki: Path, count: int) -> None:
    """One commit, because the state being recorded is "the old wiki, entire" and
    the user restoring it should have exactly one thing to name.

    Two files survive untouched and both survivals are the point: the brief is the
    user's and is most often the reason the rebuild was asked for, and the log is
    append-only — a chronology a rebuild could clear would be one that forgets its
    own most consequential event.
    """
    for tree in layout.TREES:
        shutil.rmtree(wiki / tree, ignore_errors=True)
    repo.shape(wiki)
    (wiki / layout.INDEX).write_text("", encoding="utf-8")
    log = wiki / layout.LOG
    entry = (
        f"\n## [{layout.today()}] {REBUILD_OP} | cleared the wiki and read the library again\n\n"
        f"Everything under {layout.SOURCES}/ and {layout.NOTES}/ was removed and the "
        f"catalog reset; {count} eligible video(s) follow, filed from the start. The "
        f"wiki as it stood is one commit back and can be read out of the history.\n"
    )
    log.write_text(layout.read(log) + entry, encoding="utf-8")
    repo.commit(wiki, RESET_SUBJECT)


def rebuild(home: Path, yes: bool) -> int:
    wiki = existing(home)
    eligible, _, skipped = selection(home, wiki)
    if not yes:
        return preview(wiki, eligible)
    # Before anything is destroyed: a reset whose refill cannot run is the one
    # outcome nobody wants.
    command = seams.maintainer_command(home)
    # Every step below is a git operation, and one run against a directory that
    # some *other* repository happens to contain would commit and clean there.
    # This repairs the layout contract's invariant and cannot create a wiki — a
    # missing one exited two checks ago.
    repo.ready(wiki)
    with repo.held(wiki):
        repo.commit_pending(wiki)
        reset(wiki, len(eligible))
        failed = sweep(home, wiki, command, eligible)
    return report(len(eligible) - failed, 0, skipped, failed)


# --- `tend` -------------------------------------------------------------------


def tend(home: Path, yes: bool) -> int:
    wiki = existing(home)
    command = seams.maintainer_command(home)
    repo.ready(wiki)  # the same repair `rebuild` makes, and for the same reason
    with repo.held(wiki):
        if yes:
            perform(
                home,
                wiki,
                command,
                TEND_APPLY_TASK.format(wiki=wiki, rules=_rules(TEND_OP)),
                TEND_SUBJECT,
                keep_sources=True,
            )
            return 0
        return read_only(home, wiki, command)


def read_only(home: Path, wiki: Path, command: str) -> int:
    """The reading. The user's pending work is committed first — the discard below
    takes untracked files with it, so a note typed this morning would otherwise be
    destroyed by the one verb that promised to change nothing — and then the tree
    is reset and cleaned whatever the agent did with it.

    There is no commit and no log entry: the chronology records accepted
    operations, and a run that accepted nothing is not an event in the wiki's
    history, however much the user learned from it.
    """
    pre_run = repo.commit_pending(wiki)
    code, said = seams.run_maintainer(command, home, wiki, TEND_REPORT_TASK.format(wiki=wiki))
    repo.restore(wiki, pre_run)
    if said.strip():
        print(said if said.endswith("\n") else said + "\n", end="")
    if code != 0:
        raise Failure(
            f"the tender exited {code} — a crashed reader has not read the wiki, "
            f"whatever it managed to print on the way down"
        )
    return 0
