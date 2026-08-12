---
id: SPEC-core-002
type: invariant
component: core
status: active
depends: [SPEC-core-001]
---
The derivation chain is regenerable at every link. The downloaded video is the source
of truth; the transcript is derived from it; the archive page is a pure render of
metadata plus transcript; the index is derived from archive pages alone. Deleting any
derived artifact is always recoverable by a CLI verb without re-downloading the video
(`transcribe --force` re-derives a transcript; `add` re-renders archive pages;
`reindex` rebuilds the database). Better tools later — a stronger transcription model,
a better chunking strategy — must be able to regenerate their layer for the whole
library.
