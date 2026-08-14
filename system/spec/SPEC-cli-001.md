---
id: SPEC-cli-001
type: requirement
component: cli
status: active
depends: [SPEC-core-003, SPEC-ingest-001]
---
The `tapedeck` executable exposes exactly: `add`, `search`, `ask`, `list`, `show`,
`reindex`, `rm`, `retranscribe`, `adapt-parakeet`, `doctor`, `help`, per `system/contracts/cli-surface.md`. Exit codes: 0 success, 1 operation
failure, 2 usage or validation error. Human output to stdout, diagnostics and progress
to stderr, `--json` on read-only commands. `$TAPEDECK_HOME` (default `~/Tapedeck`) is
resolved on every run; first use creates the home directories and a `config.toml`
populated with commented defaults. Adding a verb is a durable-layer change requiring a
new clause.

The default home belongs to whoever installed the tool, not to its author: a plain,
visible directory in the user's home. The archive pages are meant to be opened, so the
default sits somewhere a person browses — never hidden, never a platform-private
application directory, and never a path particular to one machine. `$TAPEDECK_HOME`
overrides it verbatim, and every path the cli touches derives from the resolved home.
The cli is the sole authority on resolving the home: where an older clause or contract
still names the pre-portability default (`~/dev/storage/tapedeck`), this clause governs
and that text is stale.

The cli orchestrates other components and never re-derives their vocabulary
(LESSON-0003): whether an id is well-formed and whether an entry's media is present are
ingest's definitions (SPEC-ingest-001), the archive page's shape is archive's, and the
cli consumes them from the owning component. Every verb that asks those questions —
`add`, `show`, `list`, `rm`, `retranscribe` — gets the same answer as the component that
owns them.
