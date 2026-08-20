---
id: SPEC-archive-001
type: requirement
component: archive
status: active
depends: [SPEC-core-002]
---
The archive page `archive/<id>.md` is a pure, deterministic render of meta.json plus
transcript.json: YAML frontmatter (id, title, channel, upload_date, duration_s, url),
then the transcript in sections. When meta.json has chapters, sections follow the
chapters; otherwise sections are five-minute blocks. Every section heading carries its
start timestamp as `[h:mm:ss](deep-link)` using the layout contract's deep-link format,
which is built from the video's own `url` — so a YouTube video's page addresses
youtube.com and a local file's page addresses that file, from one rule and with no
knowledge here of where a video came from (SPEC-ingest-005).
Identical inputs produce byte-identical output; re-rendering the whole archive from the
library must always be possible.
