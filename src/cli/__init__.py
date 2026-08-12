"""cli — the tapedeck entrypoint: `add`, `search`, `ask`, `list`, `show`, `reindex`.

Sole writer of `$TAPEDECK_HOME/config.toml`, which it creates once on first run
(system/contracts/library-layout.md). Every other verb is composition: the cli
resolves the home, then drives the components at their own subprocess boundaries.
Boundary: the `tapedeck` console script (`cli.main:main`), per
system/contracts/cli-surface.md.
"""
