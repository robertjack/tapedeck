---
id: SPEC-cli-005
type: requirement
component: cli
status: active
depends: [SPEC-cli-001]
---
`help` teaches in tiers; `-h/--help` stays the terse argparse usage it is today.

`help` with no argument prints a one-screen tour to stdout: what tapedeck is, the
four-stage derivation chain, and the everyday verbs (`add`, `search`, `ask`, `list`,
`show`, `retranscribe`) each with a one-line example. `help <verb>` prints that verb's
usage (what `<verb> --help` shows) followed by a worked example. `help manual` prints
the full manual. `help` with an unknown topic exits 2 naming the topics it knows.

`MANUAL.md` at the repo root is the manual's single source of truth, and the installed
tool carries it: when stdout is not a TTY, `help manual` output is byte-identical to
that file. When stdout is a TTY, `help` output may be ANSI-highlighted and
`help manual` is paged through `$PAGER` (falling back to `less -R`, then plain
printing); with `NO_COLOR` set or stdout piped, output contains no escape sequences
and no pager is ever invoked. The manual and the surface may not drift: every verb in
`system/contracts/cli-surface.md` appears in `MANUAL.md`.
