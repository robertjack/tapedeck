"""ingest — turn a YouTube URL into library/<id>/: the video and its metadata.

Sole writer of `library/<id>/video.*` and `library/<id>/meta.json`
(system/contracts/library-layout.md). Boundary: `python -m ingest add <url>
[--force]` for one video, `python -m ingest expand <url>` for the ids a playlist
or channel URL names.
"""

from .fetch import DEFAULT_FETCHER_COMMAND, DEFAULT_LISTER_COMMAND
from .meta import normalize
from .sources import canonical_url, resolve, video_id, video_ids

# The DEFAULT_* commands are exported for the cli's first-run config scaffolding
# (SPEC-core-004): each seam's shape is ingest's to define, config.toml is cli's
# to write. The fetcher's carries LESSON-0001 — the avc1 format preference — into
# every fresh install, so a solved 403 incident stays solved.
__all__ = [
    "DEFAULT_FETCHER_COMMAND",
    "DEFAULT_LISTER_COMMAND",
    "canonical_url",
    "normalize",
    "resolve",
    "video_id",
    "video_ids",
]
