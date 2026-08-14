"""cli — the tapedeck executable: the home, the surface, the pipeline.

Sole writer of `$TAPEDECK_HOME/config.toml` (system/contracts/library-layout.md),
which a first run scaffolds with commented defaults and every run after that
leaves alone. Everything else the cli does it does by calling the component that
owns the path: `python -m ingest add`, `python -m transcribe run`, `python -m
archive render`, `python -m index update`, `python -m ask run` — the same
boundaries those components are evaluated at.

It never re-derives another component's vocabulary (LESSON-0003). The video-id
grammar and the rule for what counts as a downloaded video are ingest's and are
imported from it; the seam defaults written into config.toml are published by the
components that run them; the model label supersession is judged on comes from
transcribe. Where the cli asks one of those questions — in `add`, `show`, `list`,
`rm`, `retranscribe` — it gets the owner's answer, not a second opinion.
"""


class Usage(ValueError):
    """A mistake in the asking — exit 2 (system/contracts/cli-surface.md)."""


class Failure(RuntimeError):
    """An operation that was attempted and did not complete — exit 1."""
