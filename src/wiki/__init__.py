"""wiki — the library's prose side: an AI-authored, git-versioned companion at
`$TAPEDECK_HOME/wiki/`.

Boundary: `python -m wiki file <id> | sync [--dry-run] | lint [--json] |
rebuild [--yes]`. Sole tapedeck-side writer of everything under `wiki/` and of
nothing outside it — in particular not `config.toml`, which is cli's
(system/contracts/wiki-layout.md). The user co-authors by hand, in any editor, at
any time, and that is the arrangement rather than a hazard: every operation
commits what it finds pending before it risks anything of its own.

The design is probabilistic inside and deterministic at the edges
(SPEC-wiki-002). A configured maintainer reads the brief and writes whatever the
brief asks of it; tapedeck reviews none of that. What it reviews is the result,
mechanically, over the whole wiki, and the answer is a commit or a rollback to
exactly where the run began. This is also the one layer SPEC-core-002 does not
govern: nothing in the library can reconstruct the particular wiki that exists,
which is why it gets git and the derived layers do not.
"""


class Usage(ValueError):
    """A mistake in the asking, or a seam that is not configured — exit 2."""


class Failure(RuntimeError):
    """An operation that was attempted and did not complete — exit 1."""
