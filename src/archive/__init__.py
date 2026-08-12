"""archive — render library metadata + transcripts into archive/<id>.md.

Sole writer of `$TAPEDECK_HOME/archive/*.md` (system/contracts/library-layout.md).
Boundary: `python -m archive render <id>` / `python -m archive render-all`.
"""

from .render import deep_link, hms, page

__all__ = ["deep_link", "hms", "page"]
