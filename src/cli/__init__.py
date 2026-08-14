"""cli — the `tapedeck` executable: one entrypoint over five components.

Owns `$TAPEDECK_HOME/config.toml` (written once, on first run, then the user's)
and the librarian's brief beside it. Nothing else: every write to `library/`,
`archive/` and `tapedeck.db` goes through the component that holds authority over
it (system/contracts/library-layout.md), invoked at the same boundary its own
durable evaluations drive.

The cli answers no question it does not own (LESSON-0003). Whether a string is a
video id and whether an entry holds a downloaded video are ingest's definitions;
the archive page's shape is archive's; the model label a transcript is judged
against is transcribe's. They are imported from their owners here and never
restated — so `add`, `show`, `list`, `rm` and `retranscribe` cannot drift apart
from the components they are asking about.
"""
