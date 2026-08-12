---
id: SPEC-ingest-001
type: requirement
component: ingest
status: active
depends: [SPEC-core-003, SPEC-core-004]
---
`add <url>` accepts any of: a full watch URL (`youtube.com/watch?v=ID`), a short URL
(`youtu.be/ID`), a shorts URL (`youtube.com/shorts/ID`), or a bare 11-character video
id — and extracts the canonical id, rejecting anything else with exit 2. It invokes the
configured fetcher, which must produce `library/<id>/video.<ext>` plus metadata; ingest
writes `library/<id>/meta.json` validating `system/contracts/meta.schema.json`
(chapters included when the source provides them). If the video directory already
exists with a video file and meta.json, the fetch is skipped unless `--force`. A failed
fetch leaves no partial `library/<id>/` behind.
