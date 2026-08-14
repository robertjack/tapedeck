"""ingest — turn a YouTube URL into library/<id>/: the video and its metadata.

Sole writer of `library/<id>/video.*` and `library/<id>/meta.json`
(system/contracts/library-layout.md). Boundary: `python -m ingest add <url>
[--force]` for one video, `python -m ingest expand <url>` for the ids a playlist
or channel URL names.

The names re-exported here are the system's shared vocabulary, published so no
other component re-derives them (LESSON-0003): the canonical id grammar, what
counts as a downloaded video, and the seam defaults. The DEFAULT_* commands are
what the cli scaffolds into a fresh config.toml (SPEC-core-004) — the fetcher's
carries LESSON-0001's avc1 format preference into every install, so a solved 403
stays solved.
"""

from .fetch import DEFAULT_FETCHER_COMMAND, DEFAULT_LISTER_COMMAND, has_video, videos
from .meta import normalize
from .sources import (
    COLLECTION,
    VIDEO,
    VIDEO_ID,
    BadRequest,
    canonical_url,
    resolve,
    video_id,
    video_ids,
)

__all__ = [
    "COLLECTION",
    "DEFAULT_FETCHER_COMMAND",
    "DEFAULT_LISTER_COMMAND",
    "VIDEO",
    "VIDEO_ID",
    "BadRequest",
    "canonical_url",
    "has_video",
    "normalize",
    "resolve",
    "video_id",
    "video_ids",
    "videos",
]
