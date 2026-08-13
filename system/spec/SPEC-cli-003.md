---
id: SPEC-cli-003
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-ingest-002, SPEC-core-003]
---
`add <url>` accepts collection URLs (playlists and channels, SPEC-ingest-002). The cli
expands the collection through ingest, then runs the standard per-video pipeline
(ingest → transcribe → archive → index) for each id in collection order. One video's
failure never stops the sweep: the cli reports the failure to stderr and moves on. At
the end it prints a one-line summary (added, skipped as already present, failed) and
exits 0 when nothing failed, 1 when anything did. Re-running the same collection URL is
the idempotent way to pick up new uploads: existing videos are skipped (SPEC-core-003),
only missing ones are fetched. `--force` on a collection is a usage error (exit 2) —
re-fetching an entire channel must be deliberate, one video at a time.
