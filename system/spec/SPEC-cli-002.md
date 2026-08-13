---
id: SPEC-cli-002
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-core-001]
---
`rm <id>` removes a video from the system. By default it deletes `library/<id>/`,
`archive/<id>.md`, and the video's presence in the index, leaving `search`, `ask`, and
`list` unaware the video ever existed. With `--media-only` it deletes only the video
file(s) under `library/<id>/`, preserving metadata, transcript, archive page, and index
entries — reclaiming disk while keeping the knowledge, at the cost of ever
re-transcribing that video. Unknown ids exit 2. Removal never touches any other
video's data.
