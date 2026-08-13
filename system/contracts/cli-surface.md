# Contract: the tapedeck CLI surface (v1)

Additive changes only; removals require superseding SPEC-cli-001.

| command | mutates library | purpose |
|---|---|---|
| `tapedeck add <url> [--force]` | yes | ingest → transcribe → archive → index for one video, or for every video of a playlist/channel URL (SPEC-cli-003; `--force` is single-video only) |
| `tapedeck search <query> [--json] [-k N]` | no | ranked timestamped excerpts with deep links |
| `tapedeck ask <question> [-k N] [--fast]` | no | librarian agent over the library (default) with post-hoc-verified citations; `--fast` = strict retrieval pipeline (SPEC-ask-001) |
| `tapedeck list [--json]` | no | one line per video: id, date, channel, title |
| `tapedeck show <id> [--json]` | no | metadata + archive path for one video |
| `tapedeck reindex` | yes (db only) | rebuild tapedeck.db from archive/ alone |
| `tapedeck rm <id> [--media-only]` | yes | remove a video everywhere (default), or delete just its media to reclaim disk while keeping the knowledge (SPEC-cli-002) |

## Conventions

- Exit codes: `0` success · `1` operation failure (fetch/transcribe/answer failed, no
  results where results were required) · `2` usage or validation error.
- Human output → stdout; diagnostics/progress → stderr; `--json` on read-only commands.
- `$TAPEDECK_HOME` resolves the library (default `~/dev/storage/tapedeck`); first use
  creates the home and a `config.toml` with commented defaults.
- Every verb is idempotent (SPEC-core-003): re-running is always safe.
