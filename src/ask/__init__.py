"""ask — a question in, an answer out, every claim traceable to a timestamp.

ask writes nothing: it reads the index's `tapedeck.db` and the `[ask]` seam in
config.toml, and prints (system/contracts/library-layout.md gives it no path of
its own). Boundary: `python -m ask run <question> [-k N]` — `answer` is the same
verb under the name the cli drives it by. Output shape, including the Sources
section tapedeck assembles rather than the model: system/contracts/ask-citations.md.
"""

from .answerer import DEFAULT_ANSWERER_COMMAND
from .citations import invented, prompt, sources_block

# The default command is exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is ask's to define, config.toml is cli's to write.
__all__ = ["DEFAULT_ANSWERER_COMMAND", "invented", "prompt", "sources_block"]
