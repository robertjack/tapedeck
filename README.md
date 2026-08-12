# tapedeck

A local video brain: `tapedeck add <url>` downloads a YouTube video, transcribes it on
this machine, and archives it as readable markdown; `tapedeck ask "question"` answers
from everything ever added, with timestamped citations that deep-link into the videos.

Built with [phx](../../phoenix/phx/) — the durable layer in `system/` (specs,
contracts, evals, lessons, provenance) is the real codebase; `src/` is generated and
disposable.

## Shape

- **Library** (user data, never in this repo): `$TAPEDECK_HOME` (default
  `~/dev/storage/tapedeck`)
  — full videos, transcripts, markdown archive, SQLite FTS index. See
  `system/contracts/library-layout.md`.
- **Derivation chain**: video → transcript → archive page → index. Every link
  regenerable; the videos are the only source of truth.
- **Components**: `ingest` (yt-dlp seam) · `transcribe` (mlx_whisper seam) · `archive`
  (pure render) · `index` (FTS5) · `ask` (retrieval + `claude -p` seam, citations
  assembled deterministically) · `cli`.

## Status

Phase 0: durable layer authored (12 clauses, 5 contracts, 6 manifests). Next: durable
evals per component, then generation. Nothing in `src/` yet — by design.
