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

## Use

```
tapedeck add <url>             # one video — or every video of a playlist/channel URL
tapedeck search "<terms>"      # timestamped excerpts with deep links (stemmed FTS)
tapedeck ask "<question>" [--video <id>]   # cited answer, optionally scoped to one video
tapedeck retranscribe [--dry-run]   # re-derive every transcript a better model supersedes
tapedeck rm <id> [--media-only]   # remove a video (or just its media, keeping the knowledge)
tapedeck list | show <id> | reindex | adapt-parakeet
```

Config (tool seams, whisper model): `~/dev/storage/tapedeck/config.toml`.

## Status

**v1.1 complete and in real use.** All six components are generated through `phx regen`
— zero hand-written implementation lines, 75 durable evals green, every generation
provenance-tracked and commit-gated. v1.1 promoted the battle-tested seam defaults into
the durable layer (LESSON-0001/0002), added playlist/channel ingestion behind a lister
seam, a parakeet-mlx adapter plus the `retranscribe` supersession sweep (real-world
verified: it re-derived the whole library after the large-v3-turbo switch), porter-stemmed
search, and `--video`-scoped ask with tightened citation verification. Next candidates:
drift monitors that write phx lessons, `tapedeck mcp` to mount the library from any
Claude surface.
