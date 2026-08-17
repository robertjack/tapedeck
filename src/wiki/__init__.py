"""wiki — the library's prose side: what the videos said, and what was made of it.

Sole tapedeck-side writer of `$TAPEDECK_HOME/wiki/**`
(system/contracts/wiki-layout.md), and the one layer SPEC-core-002 does not
govern: it is accumulated, path-dependent state, so it gets git rather than a
regenerate verb. Boundary: `python -m wiki file|sync|lint|rebuild|tend`.

The design is the same in every verb that writes — **probabilistic inside,
deterministic at the edges**. A configured agent reads the brief and edits the
wiki as it sees fit; tapedeck reviews none of its prose and all of its result,
mechanically, over the whole wiki, and either commits it or resets the tree back
to where the run began. A maintainer run is watched rather than awaited
(SPEC-wiki-007): it announces itself before it starts and its stream events
become progress on stderr as they arrive. The catalog and the chronology are
tapedeck's own bookkeeping, reconciled after the run and before the result is
judged (SPEC-wiki-008) — an agent that stays silent about either has left nothing
undone.

Two vocabularies are consumed rather than re-derived (LESSON-0003): ingest's id
grammar and rule for what counts as a downloaded video, and ask's published
`verify` boundary, which is the only reader of citation grammar in this system.
The names this component publishes to the rest of tapedeck live in
`wiki.seams` (the maintainer seam and its default) and `wiki.layout` (the pinned
tree). Nothing here imports a submodule, so those two are importable on their own.
"""

from __future__ import annotations


class Usage(ValueError):
    """The request cannot be attempted as it stands — exit 2, nothing spent."""


class Failure(RuntimeError):
    """An operation that could not complete — exit 1.

    `lines` carries every reason at once: a gate that reported one violation per
    run would turn one rejected filing into several maintainer invocations.
    """

    def __init__(self, *lines: str):
        super().__init__(lines[0] if lines else "")
        self.lines = list(lines)


class Busy(Failure):
    """Another operation holds the wiki (LESSON-0004). Refused, never queued."""


__all__ = ["Busy", "Failure", "Usage"]
