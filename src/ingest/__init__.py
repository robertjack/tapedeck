"""ingest — turn a YouTube URL into library/<id>/: the video and its metadata.

Sole writer of `library/<id>/video.*` and `library/<id>/meta.json`
(system/contracts/library-layout.md). Boundary: `python -m ingest add <url> [--force]`.
"""

from .fetch import DEFAULT_FETCHER_COMMAND
from .meta import normalize
from .sources import canonical_url, video_id

# DEFAULT_FETCHER_COMMAND is exported for the cli's first-run config scaffolding
# (SPEC-core-004): the seam's shape is ingest's to define, config.toml is cli's to
# write. It carries LESSON-0001 — the avc1 format preference — into every fresh
# install, so a solved 403 incident stays solved.
__all__ = ["DEFAULT_FETCHER_COMMAND", "canonical_url", "normalize", "video_id"]
