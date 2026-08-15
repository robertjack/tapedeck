"""The wiki's git lifecycle: history as memory and as undo (SPEC-wiki-001).

`wiki/` is its own repository — not the code repo, which holds no user data, and not
the library home, which holds gigabytes of video that nothing should be asked to
version. Every accepted operation is a commit and every rejected one is a reset, so
the two have to agree about where "back" is: the pre-run commit, the one that already
holds whatever the user typed between filings.

Going back is `reset --hard` **and** `clean -fd` together. The pages a maintainer
creates are untracked, so a reset alone leaves exactly the half-written work the
rollback exists to remove. `clean` is deliberately without `-x`: a file the user chose
to ignore is not this run's to delete.

Commits here are tapedeck's, made in the user's data repository. Hooks and signing are
skipped so a global `core.hooksPath` or a missing GPG key cannot cost a filing, and an
identity is supplied only when the machine has none of its own to offer — the wiki is
the user's repo and their name belongs on it wherever git can find it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_DIR = ".git"
FALLBACK = ("-c", "user.name=tapedeck", "-c", "user.email=tapedeck@localhost")


class GitError(RuntimeError):
    """git refused, so the operation cannot be trusted to be undoable."""


def _git(wiki: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=wiki, capture_output=True, text=True)
    except OSError as exc:
        raise GitError(f"could not run git in {wiki} — {exc}") from exc


def _must(wiki: Path, *args: str) -> str:
    result = _git(wiki, *args)
    if result.returncode != 0:
        said = (result.stderr or result.stdout or "").strip()
        raise GitError(f"`git {' '.join(args)}` failed in {wiki}: {said}")
    return result.stdout


def open_repo(wiki: Path) -> None:
    """Make sure the wiki is a repository of its own. Idempotent, and it never
    reaches for an enclosing one: a wiki inside some other checkout would have its
    history kept by a repo that knows nothing about it."""
    if not (wiki / GIT_DIR).exists():
        _must(wiki, "init", "-q")


def has_commits(wiki: Path) -> bool:
    return _git(wiki, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def dirty(wiki: Path) -> bool:
    """Is anything pending — the user's hand-edits, or a maintainer's writing?"""
    return bool(_must(wiki, "status", "--porcelain").strip())


def head(wiki: Path) -> str:
    return _must(wiki, "rev-parse", "HEAD").strip()


def commit(wiki: Path, subject: str, allow_empty: bool = False) -> str:
    """Everything in the tree under one subject; returns the commit it made."""
    _must(wiki, "add", "-A")
    options = ["--allow-empty"] if allow_empty else []
    _must(wiki, *_identity(wiki), "commit", "--no-verify", "--no-gpg-sign", "-q",
          *options, "-m", subject)
    return head(wiki)


def restore(wiki: Path, commit_sha: str) -> None:
    """Back to the pre-run commit, tracked and untracked alike."""
    _must(wiki, "reset", "--hard", "-q", commit_sha)
    _must(wiki, "clean", "-qfd")


def _identity(wiki: Path) -> tuple[str, ...]:
    configured = all(
        _git(wiki, "config", "--get", key).returncode == 0
        for key in ("user.name", "user.email")
    )
    return () if configured else FALLBACK
