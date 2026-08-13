---
id: SPEC-transcribe-001
type: requirement
component: transcribe
status: active
depends: [SPEC-core-002, SPEC-core-004]
---
Transcription turns `library/<id>/video.<ext>` into `library/<id>/transcript.json`
validating `system/contracts/transcript.schema.json`: ordered segments with start/end
seconds and text, plus the transcriber identity in `model` so a later, better model can
supersede old transcripts. The configured transcriber command receives the media path
and must yield segment-level timestamps. If transcript.json already exists it is kept
unless `--force`. A failed transcription leaves no partial transcript.json behind.

The component publishes its default transcriber command and model label (the values the
cli scaffolds into `config.toml` on first run, per SPEC-core-004), and those defaults
are the battle-tested shape of LESSON-0002, verbatim:
`mlx_whisper --model mlx-community/whisper-large-v3-turbo --condition-on-previous-text False --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"`
with model label `mlx-whisper/large-v3-turbo`.
