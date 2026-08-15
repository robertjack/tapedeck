"""index — the SQLite FTS5 index over archive-page sections.

Sole writer of `$TAPEDECK_HOME/tapedeck.db` (system/contracts/library-layout.md).
The database is derived from `archive/*.md` alone and is disposable by design:
`reindex` rebuilds the whole of it, so deleting the file loses nothing.

Boundary: `python -m index {reindex | update <id> | search <query> [-k N] [--json]}`.
"""

from .pages import Page, PageError, Section, deep_link, hms, parse

__all__ = ["Page", "PageError", "Section", "deep_link", "hms", "parse"]
