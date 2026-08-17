"""The wiki as its own git repository: the scaffold, the lock, the commits, the undo.

git is not paperwork here, it is the whole safety net. The wiki is the one layer
of tapedeck nothing can reconstruct (SPEC-wiki-001), so every accepted operation
is a commit and every rejected one is a reset — and the user's own hand-edits are
made into history *first*, as a `user edits` commit, so the rollback an agent's
failure triggers goes back to a state that still contains them. Nothing a person
typed is ever lost to a machine's failed attempt.

Going back means `git reset --hard` **and** `git clean -fd`, always both: the
pages a maintainer creates are untracked, so a reset alone leaves exactly the
half-written work the rollback exists to remove, and a clean alone leaves its
edits to tracked ones. git is indifferent to empty directories and a clean takes
`sources/` and `notes/` with it, which is not a licence to leave the wiki missing
its shape — so restoring puts them back.

"Its own repository" is checked rather than assumed, and the check is `wiki/.git`
rather than asking git where it stands: git searches upward, so a `wiki/` that is
merely a directory inside some larger repository would answer that question with
the enclosing one — and a `reset --hard` and `clean -fd` aimed there would be a
catastrophe several directories wide.

The lock is here for LESSON-0004. It lives inside the git directory, which no
reset and no clean ever reaches, it is advisory, and the operating system drops it
with the process that held it — so a crashed operation leaves nothing to clean up,
and a second mutating operation refuses at once rather than interleaving its steps
with a neighbour's and committing that neighbour's work-in-progress as `user
edits`.

**SPEC-wiki-012:** a caller may ask to wait instead of refusing. Waiting is not
interleaving — a caller that blocks before it has read or written anything has
braided nothing with the holder's commits, which is the failure LESSON-0004
records. By the time a waiter holds the lock, the wiki is exactly one committed
or rolled-back state, the same state any caller arriving a moment later would
find. The wait has no deadline of its own: it is bounded by the holder's own run,
and a deadline here would be a guess about how long a neighbour's maintainer
takes to think.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import sys
from pathlib import Path

from . import Busy, Failure
from .layout import BRIEF, DEFAULT_BRIEF, GIT, INDEX, LOG, TREES

SCAFFOLD_SUBJECT = "wiki scaffold"
USER_EDITS = "user edits"
LOCK = "tapedeck-wiki.lock"
# Used only where this machine's git has no identity of its own: a user who
# configured one still commits under it, in a repository that is theirs to push.
FALLBACK = ("tapedeck", "tapedeck@localhost")
BUSY_MESSAGE = (
    "another wiki operation is running and holds this wiki until it commits or "
    "rolls back — re-run when it is done; `tapedeck wiki sync` picks up whatever "
    "is left"
)
WAITING_MESSAGE = (
    "the wiki is held by another operation — waiting for it to commit or roll back"
)


def _run(wiki: Path, args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=wiki, capture_output=True, text=True)
    except OSError as exc:
        raise Failure(f"could not run git in {wiki} — {exc}") from exc


_IDENTITY: dict[str, list[str]] = {}


def _settings(wiki: Path) -> list[str]:
    """What every call here carries. Signing is off because a filing that blocks
    on a passphrase prompt is one nobody is there to answer; an identity is
    supplied only where the machine has none of its own, so a user who configured
    one still commits under it. The probe is asked once per run — a sweep of forty
    should not spend eighty subprocesses learning the same answer."""
    key = str(wiki)
    if key not in _IDENTITY:
        settings = ["-c", "commit.gpgsign=false"]
        if _run(wiki, ["var", "GIT_COMMITTER_IDENT"]).returncode != 0:
            name, email = FALLBACK
            settings += ["-c", f"user.name={name}", "-c", f"user.email={email}"]
        _IDENTITY[key] = settings
    return _IDENTITY[key]


def git(wiki: Path, *args: str) -> str:
    result = _run(wiki, [*_settings(wiki), *args])
    if result.returncode != 0:
        complaint = (result.stderr or result.stdout).strip()
        raise Failure(f"git {args[0]} failed in {wiki}: {complaint}")
    return result.stdout


def exists(wiki: Path) -> bool:
    return wiki.is_dir()


def versioned(wiki: Path) -> bool:
    """`.git` is a directory in an ordinary repository and a file in a worktree;
    either means this wiki keeps its own history, which is the invariant."""
    return (wiki / GIT).exists()


def shape(wiki: Path) -> None:
    """The two directories the layout pins, which git will not keep for us."""
    for tree in TREES:
        (wiki / tree).mkdir(parents=True, exist_ok=True)


def ready(wiki: Path) -> None:
    """Scaffold on first use and never again: a wiki that is already versioned is
    left exactly as the user left it, its brief above all. A `wiki/` that exists
    without a repository is not left half-made either — it is given the history
    every later step compares against, and the files it is already carrying are
    kept as they are."""
    if versioned(wiki):
        return
    wiki.mkdir(parents=True, exist_ok=True)
    shape(wiki)
    _create(wiki / BRIEF, DEFAULT_BRIEF)
    _create(wiki / INDEX, "")
    _create(wiki / LOG, "")
    # Plainly, not through git(): the identity probe there wants a repository to
    # ask inside, and this is the call that makes one.
    made = _run(wiki, ["-c", "init.defaultBranch=main", "init", "-q"])
    if made.returncode != 0:
        raise Failure(
            f"could not make {wiki} a git repository: {(made.stderr or made.stdout).strip()}"
        )
    commit(wiki, SCAFFOLD_SUBJECT)


def _create(path: Path, text: str) -> None:
    """Write a file only if it is not already there — the scaffold's whole rule."""
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        pass


def dirty(wiki: Path) -> bool:
    return bool(_run(wiki, ["status", "--porcelain"]).stdout.strip())


def commit(wiki: Path, subject: str) -> None:
    """Stage everything and record it. Hooks are skipped: a wiki operation must
    not fail on a hook the user wrote for something else."""
    git(wiki, "add", "-A")
    made = _run(wiki, [*_settings(wiki), "commit", "--no-verify", "-q", "-m", subject])
    if made.returncode != 0 and dirty(wiki):
        raise Failure(
            f"could not commit {subject!r} in {wiki}: {(made.stderr or made.stdout).strip()}"
        )


def commit_pending(wiki: Path) -> str:
    """Whatever the user left in the working tree becomes history before this run
    touches anything, and that commit is the pre-run commit every later step
    refers to — so every undo stops on the far side of a person's writing."""
    if dirty(wiki):
        commit(wiki, USER_EDITS)
    return head(wiki)


def head(wiki: Path) -> str:
    return git(wiki, "rev-parse", "HEAD").strip()


def restore(wiki: Path, commitish: str) -> None:
    """Back to the pre-run commit, taking untracked work with it."""
    git(wiki, "reset", "--hard", "-q", commitish)
    git(wiki, "clean", "-qfd")
    shape(wiki)


def _git_dir(wiki: Path) -> Path:
    inside = wiki / GIT
    if inside.is_dir():
        return inside
    resolved = _run(wiki, ["rev-parse", "--absolute-git-dir"])
    if resolved.returncode != 0:
        raise Failure(f"{wiki} is not a git repository of its own")
    return Path(resolved.stdout.strip())


@contextlib.contextmanager
def held(wiki: Path, wait: bool = False):
    """Hold the wiki for exactly one operation.

    Without `wait`, a caller that finds the lock taken refuses at once: the
    refusal costs nothing a sweep cannot recover — filing is idempotent and the
    next `sync` converges — while waiting by default would put two operations'
    commits into each other, the failure LESSON-0004 is made of.

    With `wait=True` (SPEC-wiki-012, `file --wait` alone), a caller that finds the
    lock taken announces that it is waiting — the one new silence this flag
    introduces, and one indistinguishable from a hang without the line — and then
    blocks on the same lock until the holder commits or rolls back. It has read
    nothing and written nothing while it waited, so by the time it holds the lock
    the wiki is exactly one committed or rolled-back state: no interleaving, only
    a caller that arrived late.
    """
    handle = os.open(_git_dir(wiki) / LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if not wait:
                raise Busy(BUSY_MESSAGE) from exc
            print(WAITING_MESSAGE, file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)  # blocks until the holder releases it
        yield
    finally:
        os.close(handle)
