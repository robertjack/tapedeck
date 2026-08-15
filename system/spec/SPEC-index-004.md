---
id: SPEC-index-004
type: constraint
component: index
status: active
depends: [SPEC-index-001, SPEC-index-003]
---
The database declares its schema version and the index refuses what it cannot read.
`reindex` stamps `PRAGMA user_version` with the implementation's current schema
version (nonzero). `search` and `update` refuse to operate on a database whose
`user_version` differs from the version this implementation writes: nonzero exit and
a diagnostic on stderr naming `reindex` as the remedy — never a silent misread of
rows laid out by another schema. `reindex` itself is exempt: it deletes and rebuilds
(SPEC-index-001), which is the migration.

Provenance of this clause: the deletion-test rebuild (2026-08-15). The original
implementation carried this guard, but no clause or index eval demanded it — the
knowledge lived only in `src/` (the exact violation SPEC-core-001 forbids), attested
only by a precondition inside *ask's* eval suite. A regenerated index legitimately
omitted it, and every downstream component stalled on a rule written nowhere.
