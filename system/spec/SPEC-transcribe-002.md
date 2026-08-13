---
id: SPEC-transcribe-002
type: requirement
component: transcribe
status: active
depends: [SPEC-transcribe-001, SPEC-core-004]
---
`from-parakeet` adapts parakeet-mlx JSON to the whisper shape the transcriber seam
requires: parakeet JSON on stdin (`{"text": ..., "sentences": [{"text", "start",
"end", ...}, ...]}`), whisper-shaped JSON on stdout (`{"segments": [{"start", "end",
"text"}, ...]}`), order and timestamps preserved, token detail dropped. Input that is
not parakeet-shaped exits 1 with nothing on stdout. This keeps a parakeet transcriber
a pure config edit (the seam principle): the scaffolded `config.toml` documents, in a
comment beside the whisper default, the alternative transcriber command
`parakeet-mlx --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA" && tapedeck adapt-parakeet < "$(dirname "$TAPEDECK_OUT")/video.json" > "$TAPEDECK_OUT"`
with model label `parakeet-mlx/tdt-0.6b-v3` (parakeet names its output after the
input file, so `video.<ext>` yields `video.json`).
