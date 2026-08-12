"""index — the SQLite FTS5 index over archive-page sections.

Sole writer of `$TAPEDECK_HOME/tapedeck.db` (system/contracts/library-layout.md),
derived from `archive/*.md` alone and disposable: `reindex` rebuilds it whole.
Boundary: `python -m index {reindex | update <id> | search <query> [-k N] [--json]}`.
"""

from .pages import Page, Section, deep_link, hms, parse

__all__ = ["Page", "Section", "deep_link", "hms", "parse"]
