"""ingest — resolve a YouTube address and fetch it into library/<id>/.

Sole writer of `library/<id>/video.*` and `library/<id>/meta.json`
(system/contracts/library-layout.md). Boundary: `python -m ingest add <url> [--force]`.
"""

from .fetch import DEFAULT_FETCHER_COMMAND
from .meta import normalize
from .sources import canonical_id, watch_url

# DEFAULT_FETCHER_COMMAND is exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is ingest's to define, the file is cli's to write.
__all__ = ["DEFAULT_FETCHER_COMMAND", "canonical_id", "normalize", "watch_url"]
