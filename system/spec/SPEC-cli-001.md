---
id: SPEC-cli-001
type: requirement
component: cli
status: active
depends: [SPEC-core-003]
---
The `tapedeck` executable exposes exactly: `add`, `search`, `ask`, `list`, `show`,
`reindex`, per `system/contracts/cli-surface.md`. Exit codes: 0 success, 1 operation
failure, 2 usage or validation error. Human output to stdout, diagnostics and progress
to stderr, `--json` on read-only commands. `$TAPEDECK_HOME` (default `~/Tapedeck`) is
resolved on every run; first use creates the home directories and a `config.toml`
populated with commented defaults. Adding a verb is a durable-layer change requiring a
new clause.
