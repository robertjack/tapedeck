# Contract: the tapedeck CLI surface (v1)

Additive changes only; removals require superseding SPEC-cli-001.

| command | mutates library | purpose |
|---|---|---|
| `tapedeck add <url> [--force]` | yes | ingest → transcribe → archive → index for one video, or for every video of a playlist/channel URL (SPEC-cli-003; `--force` is single-video only) |
| `tapedeck search <query> [--json] [-k N]` | no | ranked timestamped excerpts with deep links |
| `tapedeck ask <question> [-k N] [--fast] [--video <id>]` | no | librarian agent over the library (default) with post-hoc-verified citations; `--fast` = strict retrieval pipeline (SPEC-ask-001); `--video` scopes either mode to one video (SPEC-ask-003) |
| `tapedeck list [--json]` | no | one line per video: id, date, channel, title |
| `tapedeck show <id> [--json]` | no | metadata + archive path for one video |
| `tapedeck reindex` | yes (db only) | rebuild tapedeck.db from archive/ alone |
| `tapedeck rm <id> [--media-only]` | yes | remove a video everywhere (default), or delete just its media to reclaim disk while keeping the knowledge (SPEC-cli-002) |
| `tapedeck retranscribe [--dry-run]` | yes | re-derive transcript → archive → index for every video whose transcript model label differs from the configured `[transcribe].model` (SPEC-cli-004) |
| `tapedeck adapt-parakeet` | no | stdin→stdout filter: parakeet-mlx JSON to the whisper shape the transcriber seam requires (SPEC-transcribe-002) |
| `tapedeck doctor [--json]` | no | read-only diagnosis: each config seam's head executable on PATH, plus ffmpeg, the library home, SQLite FTS5, and the platform against the configured transcriber (SPEC-cli-007); the `[ask]` seams are optional and never fail the exit code |
| `tapedeck setup [--yes]` | yes (home scaffold only) | first-run wizard: scaffold the home and name it, report exactly what `doctor` reports, then print the platform remedy command for every required gap; without `--yes` it executes nothing (exit 1 if anything required is missing, 0 when `ready`), with `--yes` it runs those remedies and re-checks (SPEC-cli-008) |
| `tapedeck help [<verb> \| manual]` | no | tiered teaching: one-screen tour, per-verb usage + example, or the full MANUAL.md paged (SPEC-cli-005); `-h/--help` stays terse |

## Conventions

- Exit codes: `0` success · `1` operation failure (fetch/transcribe/answer failed, no
  results where results were required) · `2` usage or validation error.
- Human output → stdout; diagnostics/progress → stderr; `--json` on read-only commands.
- `$TAPEDECK_HOME` resolves the library (default `~/Tapedeck`, a visible directory in
  the user's home — never a path particular to one machine); first use creates the home
  and a `config.toml` with commented defaults.
- Global options: `--version` prints the installed version from package metadata and
  exits 0 without resolving or creating a library home (SPEC-cli-006); `-h/--help`
  prints terse argparse usage.
- Every verb is idempotent (SPEC-core-003): re-running is always safe.
- Installing anything on the user's machine happens only under an explicit `--yes`, and
  only the commands tapedeck printed first (SPEC-cli-008). The remedy commands are a
  config seam like every other tool: `[setup]` `remedy.<executable>` in `config.toml`,
  shipped with brew/uv defaults.
