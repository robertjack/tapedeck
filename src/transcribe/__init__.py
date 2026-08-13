"""transcribe — derive library/<id>/transcript.json from the video that is here.

Sole writer of `library/<id>/transcript.json` (system/contracts/library-layout.md).
Boundary: `python -m transcribe run <id> [--force]`.
"""

from .document import normalize, write
from .transcriber import DEFAULT_MODEL, DEFAULT_TRANSCRIBER_COMMAND

# The two defaults are exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is transcribe's to define, config.toml is
# cli's to write. They carry LESSON-0002 — turbo weights, conditioning off, and a
# label that names both — into every fresh install, so a repetition-loop incident
# that has been solved once stays solved.
__all__ = ["DEFAULT_MODEL", "DEFAULT_TRANSCRIBER_COMMAND", "normalize", "write"]
