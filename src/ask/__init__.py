"""ask — a question in, an answer out, every claim traceable to a timestamp.

Two modes, one rule. By default a librarian agent is run *in* the library home and
reads it however it likes; tapedeck checks its citations mechanically before letting
the answer through. `--fast` keeps the strict pipeline: retrieve first, answer only
from what was retrieved, Sources assembled by tapedeck. Freedom to retrieve, no
freedom to fabricate (SPEC-ask-001, SPEC-ask-002).

ask writes nothing — the layout contract gives it no path of its own. Boundary:
`python -m ask run <question> [-k N] [--fast]` (`answer` is the same verb under the
name the cli drives it by). Output shape, both modes: contracts/ask-citations.md.
"""

from .seams import DEFAULT_ANSWERER_COMMAND, DEFAULT_LIBRARIAN_COMMAND

# Exported for the cli's first-run config scaffolding (SPEC-core-004): the shape of
# each seam is ask's to define, config.toml is the cli's to write.
__all__ = ["DEFAULT_ANSWERER_COMMAND", "DEFAULT_LIBRARIAN_COMMAND"]
