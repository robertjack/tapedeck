---
id: SPEC-core-003
type: constraint
component: core
status: active
depends: []
---
Every verb is idempotent. Re-running any command is always safe: `add` on an
already-ingested video skips the download and refreshes derived artifacts (`--force`
re-fetches); `reindex` produces the same database from the same archive; no verb ever
corrupts or duplicates library state when interrupted and re-run.
