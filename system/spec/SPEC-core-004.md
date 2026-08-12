---
id: SPEC-core-004
type: constraint
component: core
status: active
depends: []
---
External tools sit behind configuration seams. The fetcher (default: yt-dlp), the
transcriber (default: mlx_whisper), and the answerer (default: `claude -p`) are invoked
via command templates in `$TAPEDECK_HOME/config.toml` sections `[ingest]`,
`[transcribe]`, and `[ask]`. Durable evaluations inject fake commands through these
seams; no component may hardcode an external tool invocation. Defaults are written into
config.toml on first run so users can see and edit them.
