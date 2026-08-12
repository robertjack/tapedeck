---
id: SPEC-index-001
type: requirement
component: index
status: active
depends: [SPEC-core-002, SPEC-archive-001]
---
`tapedeck.db` is a SQLite database with an FTS5 index over chunks, where a chunk is one
archive-page section (its video id, section start seconds, section title, and text).
The database is derived from `archive/*.md` alone: `reindex` deletes and rebuilds it
completely, and the deletion test is literal — removing tapedeck.db loses nothing.
Incremental updates after `add` must produce the same rows for a video as a full
reindex would.
