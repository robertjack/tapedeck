---
id: SPEC-cli-006
type: requirement
component: cli
status: active
depends: [SPEC-cli-001]
---
`tapedeck --version` prints the installed version to stdout and exits 0.

The version is read from the installed distribution's metadata (`importlib.metadata`),
which makes `pyproject.toml` the single source of truth. No version string is duplicated
in the source, and there is no hardcoded fallback constant: a build whose own metadata
cannot be read is a broken install and must say so on stderr with exit 1 rather than
report a number it invented.

`--version` is a global option, not a verb. It is answered before any library work: it
requires no `$TAPEDECK_HOME`, creates no home, reads no `config.toml`, and works from
any directory. It is the first thing a stranger runs after installing, so it must never
depend on this machine's layout or on any external tool being present.

**Amended for the distribution round:** the installed distribution is named
`tapedeck-cli` — PyPI's `tapedeck` belongs to an unrelated project, and installing a
squatted name is how a stranger gets somebody else's software — while the executable,
the config, the library layout and every piece of user-facing vocabulary stay
`tapedeck`. The metadata `--version` reads is `tapedeck-cli`'s; nothing else about
this clause moves.
