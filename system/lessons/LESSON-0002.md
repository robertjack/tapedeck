---
id: LESSON-0002
components: [transcribe]
source: production
evidence: 2026-08-12 pilot: whisper large-v3 fell into a severe repetition loop on a long video; large-v3-turbo with --condition-on-previous-text False transcribed the same video cleanly and faster. Fix lived only in the pilot library's hand-edited config.toml until this lesson.
status: active
---
mlx_whisper large-v3 with default conditioning falls into repetition loops on long videos. The default transcriber the component ships is whisper large-v3-turbo with --condition-on-previous-text False, labelled mlx-whisper/large-v3-turbo — and the model label must always name the configuration actually in use, because transcript supersession is judged on that label.
