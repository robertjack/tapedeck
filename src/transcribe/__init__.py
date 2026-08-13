"""transcribe — derive library/<id>/transcript.json from the video that is here.

Sole writer of `library/<id>/transcript.json` (system/contracts/library-layout.md).
Boundary: `python -m transcribe run <id> [--force]`, plus the `from-parakeet`
filter that keeps a change of transcriber inside config.toml.
"""

from .document import normalize, write
from .parakeet import adapt
from .transcriber import (
    DEFAULT_MODEL,
    DEFAULT_TRANSCRIBER_COMMAND,
    PARAKEET_MODEL,
    PARAKEET_TRANSCRIBER_COMMAND,
)

# The defaults are exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is transcribe's to define, config.toml is
# cli's to write. The whisper pair carries LESSON-0002 — turbo weights,
# conditioning off, and a label that names both — into every fresh install, so a
# repetition-loop incident that has been solved once stays solved. The parakeet
# pair is the documented alternative beside it (SPEC-transcribe-002): proof that
# swapping transcriber is an edit to a config file and not to tapedeck.
__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_TRANSCRIBER_COMMAND",
    "PARAKEET_MODEL",
    "PARAKEET_TRANSCRIBER_COMMAND",
    "adapt",
    "normalize",
    "write",
]
