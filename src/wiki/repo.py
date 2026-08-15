"""The wiki's own git repository: history is its memory and its recovery at once.

`wiki/` is initialized by tapedeck and nested inside nothing — not the code repo,
which holds no user data, and not the library, which holds gigabytes of video
that nothing should be asked to version. Every accepted operation is a commit, so
the user can read what changed, revert a filing they dislike, and push the whole
thing to a remote of their own without tapedeck knowing or caring.

This module is therefore the whole of what "undone" means here: `git reset
--hard` **and** `git clean -fd`, back to the pre-run commit rather than the one
before it. Both halves matter. A maintainer's new pages are untracked, so a reset
alone leaves exactly the half-written work the rollback exists to remove; and the
pre-run commit is the one that already holds the user's pending hand-edits, so no
machine's failed attempt takes a person's writing with it. Git is indifferent to
empty directories and a clean will take `sources/` and `notes/` with it, which is
not a licence to leave the wiki missing its shape — so restoring puts them back.

Scaffolding happens once and never again (SPEC-wiki-001). The brief below is a
default in exactly the sense `config.toml` is one: written so there is something
to read and edit on the first day, and never rewritten, reformatted or migrated
after that. A brief the user has replaced wholesale is the intended end state.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import Failure
from .layout import BRIEF, INDEX, LOG, NOTES, SOURCES

USER_EDITS = "user edits"
SCAFFOLD = "wiki scaffold"
# Used only when the machine has no identity of its own to commit under; a wiki
# that cannot be committed to is a wiki that cannot be filed into.
FALLBACK = ("tapedeck", "tapedeck@localhost")


class GitError(Failure):
    """git could not do something the wiki's bookkeeping depends on."""


DEFAULT_BRIEF = """\
# The tapedeck wiki

You maintain this wiki. It is the prose side of a video library: what the videos
said, what it amounts to, and how it all connects. Each time tapedeck files a
video you are run here, in this directory, with one video to read about and the
whole wiki to write into.

This file is yours — the person whose library this is — to rewrite. tapedeck
wrote this first version so there would be something here on day one, and will
never touch it again.

## Where things are

- `sources/<video-id>.md` — one page per filed video. Its existence is how
  tapedeck knows that video has been filed, so the page you were asked for has to
  be there when you stop.
- `notes/` — everything else: ideas, arguments, people, open questions. How they
  are named and foldered is this file's business, which is to say yours.
- `index.md` — the catalog: one markdown-linked line per page.
- `log.md` — the chronology. Appended to, never edited.

Your reading material sits outside the wiki and is read-only.
`$TAPEDECK_ARCHIVE_PAGE` is the page for the video being filed — its headings
carry a deep link into every section — `$TAPEDECK_HOME/archive/` holds every
other one, and `$TAPEDECK_VIDEO_ID` is the video in question.

## What is checked before your work is kept

Everything you write lands as one commit or is thrown away entire. The checks are
mechanical, they run over the whole wiki rather than over your diff, and each one
is about something a later reader would otherwise trip over:

1. This file is never edited. It is your instructions; an agent that may rewrite
   its own instructions has none.
2. `sources/<video-id>.md` exists and carries at least one deep link into the
   video it is about. Copy those links out of the archive page's headings — never
   reconstruct one from memory.
3. Every wiki link resolves. A wiki link is a page's filename without `.md`,
   wrapped in doubled square brackets, matched case-sensitively, and satisfied by
   a page anywhere in here; put a display alias after a `|` if you want one.
4. Every deep link anywhere in the wiki names a real video at a moment inside it.
   Links are verified against the library — in this file too, so an example URL
   written out in full here would be read as a claim and checked as one.
5. `index.md` links every page except these three.
6. `log.md` still begins with exactly what it said before, and has gained an
   entry of the form `## [YYYY-MM-DD] file | <video-id>` followed by whatever you
   want to say about the filing.

## House style — replace this with your own

A starting point, and the part of this file most worth rewriting.

- A source page says what the video is, what it actually argues, and what it
  connects to. Quote sparingly, and anchor each quote to its moment.
- A claim earns its own note in `notes/` when a second video touches it. One idea
  per page; the filename is the idea, in lower-case-with-hyphens.
- Link generously. A wiki is worth re-reading for its edges, not its pages.
- Write for the person who comes back in a year remembering only that they
  watched something about this.
"""


class Repo:
    """The wiki directory, and the git operations the wiki's rules are made of."""

    def __init__(self, path: Path):
        self.path = path
        self._settings: list[str] | None = None

    # --- plumbing ---

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", *args], cwd=self.path, capture_output=True, text=True
            )
        except OSError as exc:
            raise GitError(f"could not run git in {self.path} — {exc}") from exc

    def _config(self) -> list[str]:
        """Overrides every git call here carries. Signing is off because a filing
        that blocks on a passphrase prompt is a filing nobody is there to answer;
        an identity is supplied only when the machine has none of its own, so a
        user who configured one still commits under it."""
        if self._settings is None:
            settings = ["-c", "commit.gpgsign=false"]
            if self._run(["var", "GIT_COMMITTER_IDENT"]).returncode != 0:
                name, email = FALLBACK
                settings += ["-c", f"user.name={name}", "-c", f"user.email={email}"]
            self._settings = settings
        return self._settings

    def git(self, *args: str) -> str:
        result = self._run([*self._config(), *args])
        if result.returncode != 0:
            complaint = (result.stderr or result.stdout).strip()
            raise GitError(f"git {args[0]} failed in {self.path}: {complaint}")
        return result.stdout

    # --- the wiki's shape ---

    @property
    def exists(self) -> bool:
        # `.git` is a directory in an ordinary repo and a file in a worktree; both
        # mean the same thing here, which is that this wiki is already versioned.
        return (self.path / ".git").exists()

    def shape(self) -> None:
        """The two directories the layout pins, which git does not keep for us."""
        for name in (SOURCES, NOTES):
            (self.path / name).mkdir(parents=True, exist_ok=True)

    def ensure(self) -> None:
        """Scaffold on first use and never again: a wiki that is already there is
        left exactly as the user left it, its brief above all."""
        if self.exists:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        self.shape()
        _create(self.path / BRIEF, DEFAULT_BRIEF)
        _create(self.path / INDEX, "")
        _create(self.path / LOG, "")
        # Plainly, not through git(): the identity probe there wants a repository
        # to ask inside, and this is the call that makes one.
        made = self._run(["init", "-q"])
        if made.returncode != 0:
            raise GitError(
                f"could not make {self.path} a git repository: "
                f"{(made.stderr or made.stdout).strip()}"
            )
        self.commit(SCAFFOLD)

    # --- history ---

    def dirty(self) -> bool:
        return bool(self._run(["status", "--porcelain"]).stdout.strip())

    def commit(self, subject: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject)

    def commit_pending(self) -> None:
        """Whatever the user left in the working tree becomes history before this
        run touches anything, so the state a rollback lands on already holds it."""
        if self.dirty():
            self.commit(USER_EDITS)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def restore(self, commit: str) -> None:
        self.git("reset", "--hard", "-q", commit)
        self.git("clean", "-qfd")
        self.shape()


def _create(path: Path, text: str) -> None:
    """Write a file only if it is not already there — the scaffold's whole rule."""
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        pass
