"""wiki — the library's prose side: pages an agent writes and a gate admits.

Sole writer of `$TAPEDECK_HOME/wiki/**` (system/contracts/wiki-layout.md), and the
one layer of tapedeck that is versioned rather than regenerable (SPEC-wiki-001): a
transcript can be re-derived and thrown away, a wiki can only be kept, so its git
history is both its memory and its undo. Boundary: `python -m wiki file <id>`.

`DEFAULT_MAINTAINER_COMMAND` is published from here for the cli to scaffold into a
fresh config.toml, as the owner of every seam publishes its own default
(SPEC-core-004) — the shape of the seam belongs to the component that runs it.
"""

from .seams import DEFAULT_MAINTAINER_COMMAND, MAINTAINER_KEY, SECTION

__all__ = ["DEFAULT_MAINTAINER_COMMAND", "MAINTAINER_KEY", "SECTION"]
