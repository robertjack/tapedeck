---
id: SPEC-index-003
type: requirement
component: index
status: active
depends: [SPEC-index-001]
---
The FTS index stems English: the chunk index uses FTS5's porter tokenizer over
unicode61, so morphological variants match — "video" finds "videos", "transcribe"
finds "transcribing". `reindex` is the migration for any pre-porter database
(SPEC-index-001: rebuilding from archive/ loses nothing), and incremental updates
produce the same rows and the same matches as a full reindex under the same
tokenizer.
