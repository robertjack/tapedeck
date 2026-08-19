"""cli — the tapedeck entrypoint.

Argument parsing, `$TAPEDECK_HOME` resolution and first-run `config.toml`
scaffolding, and orchestration of the other components: ingest -> transcribe
-> archive -> index for `add`, plus doctor/setup/help and pass-through routing
for search/ask/reindex/wiki. Boundary: the `tapedeck` executable, and
`python -m cli` (system/contracts/cli-surface.md).

This component never re-derives another's vocabulary (LESSON-0003): the video
id grammar and what counts as a downloaded video are ingest's, the h:mm:ss
duration format is archive's, the wiki's filed-state marker and its seam
default are wiki's — all imported, never rewritten here.
"""
