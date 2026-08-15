"""Component boundary: `python -m wiki file <id>`.

Sole writer of `$TAPEDECK_HOME/wiki/**` and of nothing else — config.toml is cli's
file and the library is read-only here (SPEC-core-001). Exit codes follow the cli
surface: 0 success, 1 operation failure, 2 usage or config error; everything this
command has to say goes to stderr, because its output is the wiki.

The order below is the design, and each step is there because of the one after it
(SPEC-wiki-002). The cheap refusals come first, so nothing probabilistic is ever spent
on a question already settled: an id the grammar rejects or the library does not hold,
a page archive has not rendered yet, a video whose sources page says it is filed. Then
the wiki is scaffolded if it is absent, and whatever the user has typed into it since
the last run is committed as theirs — because the two steps that follow may have to
undo everything, and an undo that reaches past a person's own writing is the one
failure this component must never have. Only then does the maintainer run, and only
what the gate accepts is kept.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from ingest import VIDEO_ID

from . import gate, repo, scaffold, seams

DEFAULT_HOME = "~/dev/storage/tapedeck"
LIBRARY, ARCHIVE, WIKI = "library", "archive", "wiki"
PAGE_SUFFIX = ".md"
SCAFFOLD_COMMIT = "wiki scaffold"
USER_COMMIT = "user edits"

USAGE_ERRORS = (seams.ConfigError,)
FAILURES = (seams.MaintainerFailed, repo.GitError, OSError)


class Failure(RuntimeError):
    """An operation that could not complete; carries the process exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser().resolve()


def file_video(video_id: str) -> int:
    home = home_dir()
    archive_page = _ready(home, video_id)
    wiki = home / WIKI

    if (wiki / scaffold.SOURCES / f"{video_id}{PAGE_SUFFIX}").is_file():
        # The sources page is the filed-state marker, so this costs nothing and
        # changes nothing: filing a whole library is a loop worth re-running.
        print(f"{video_id} is already filed in the wiki — nothing to do", file=sys.stderr)
        return 0

    command = seams.maintainer_command(home)
    fresh = scaffold.ensure(wiki)
    repo.open_repo(wiki)
    if repo.dirty(wiki) or not repo.has_commits(wiki):
        repo.commit(wiki, SCAFFOLD_COMMIT if fresh else USER_COMMIT, allow_empty=True)
    pre_run = repo.head(wiki)
    before = gate.snapshot(wiki)

    try:
        seams.run_maintainer(
            command, home, wiki, video_id, archive_page, task(video_id, archive_page)
        )
    except seams.MaintainerFailed as exc:
        repo.restore(wiki, pre_run)
        raise Failure(f"{exc}\nthe wiki is back at {pre_run[:7]}, unchanged") from exc

    problems = gate.review(wiki, home, video_id, before)
    if problems:
        repo.restore(wiki, pre_run)
        raise Failure(
            "this filing was not accepted:\n  "
            + "\n  ".join(problems)
            + f"\nnothing was kept — the wiki is back at {pre_run[:7]}"
        )
    repo.commit(wiki, f"{WIKI} file {video_id}", allow_empty=True)
    return 0


def _ready(home: Path, video_id: str) -> Path:
    """Everything that can be settled by looking. The id grammar is ingest's, so a
    malformed one is refused in its words, not in a copy of its rule (LESSON-0003)."""
    if not VIDEO_ID.fullmatch(video_id):
        raise Failure(
            f"{video_id!r} is not a video id — tapedeck's ids are the 11 characters "
            "YouTube gives a video",
            code=2,
        )
    if not (home / LIBRARY / video_id).is_dir():
        raise Failure(
            f"no video {video_id!r} in the library — `tapedeck list` shows what is here",
            code=2,
        )
    page = home / ARCHIVE / f"{video_id}{PAGE_SUFFIX}"
    if not page.is_file():
        # In the library but not yet rendered: a job that cannot be done yet rather
        # than a mistyped id, because the archive page is what the maintainer reads.
        raise Failure(
            f"no archive page for {video_id} at {page} — run `tapedeck add {video_id}` "
            "to render it, then file again"
        )
    return page


def task(video_id: str, archive_page: Path) -> str:
    """What the maintainer is told. The conventions are deliberately not here: they
    live in the wiki's own CLAUDE.md, which is the user's to write. This says what the
    job is and what the gate will refuse, and nothing about how to think."""
    return f"""\
File the library video {video_id} into this wiki.

You are standing in the wiki. Read `CLAUDE.md` first: it is the brief, and its
conventions decide everything about how you write here — what earns a page, how notes
are named and organised, how deep any of it goes. Then read the video's archive page:

    {archive_page}

It carries the metadata as frontmatter and then one section per chapter, each heading
a `[h:mm:ss](deep link)` into the recording itself. Read it properly: a page built out
of the headings alone is a table of contents, not a filing. Write the source page,
write or extend whatever notes the brief says this video earns, and link them up.

Six things tapedeck checks mechanically when you are done. A single failure throws
away the whole run, so none of them is optional:

1. `sources/{video_id}.md` exists and carries at least one deep link to {video_id}
   itself, in the form `https://www.youtube.com/watch?v={video_id}&t=<seconds>s`.
2. Every deep link anywhere in the wiki points at a video the library really holds,
   at a moment inside its real length. Take every id and offset off the page you read
   it on; never reconstruct one from memory.
3. Every wikilink resolves — the target matched exactly and case-sensitively against
   some page's filename with `.md` removed.
4. `index.md` links every page in the wiki except `CLAUDE.md`, `index.md` and
   `log.md`. Add a line for each page you create.
5. `log.md` is append-only. Append one entry beginning
   `## [{date.today().isoformat()}] file | {video_id}` and change not one word above it.
6. `CLAUDE.md` is untouched. It is the user's instructions to you; edit it in any way
   and this filing is rejected.
"""


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="wiki", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    filing = sub.add_parser("file", help="file one library video into the wiki")
    filing.add_argument("video_id")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    try:
        return file_video(args.video_id)
    except USAGE_ERRORS as exc:
        return _report(exc, 2)
    except FAILURES as exc:
        return _report(exc, 1)
    except Failure as exc:
        return _report(exc, exc.code)


def _report(exc, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
