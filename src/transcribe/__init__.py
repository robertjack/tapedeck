"""transcribe — derive library/<id>/transcript.json from the downloaded video.

Sole writer of `library/<id>/transcript.json`
(system/contracts/library-layout.md). Boundary: `python -m transcribe run <id> [--force]`.
"""

from .document import normalize
from .transcriber import DEFAULT_MODEL, DEFAULT_TRANSCRIBER_COMMAND

# The defaults are exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is transcribe's to define, config.toml is cli's
# to write. They travel together — the model label names what the command runs.
__all__ = ["DEFAULT_MODEL", "DEFAULT_TRANSCRIBER_COMMAND", "normalize"]
