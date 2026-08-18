---
id: SPEC-cli-012
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-cli-003, SPEC-cli-009, SPEC-ingest-004]
---
`add` closes each video's account in the user's terms, and routes `--verbose` down to
the tool. Two small clauses, both display, both stderr; stdout and the summary line
still mean exactly what they meant.

**The close-out line.** After a video's four-stage chain succeeds inside `add`, one
stderr line says what was just added the way the user thinks of it — the video's
title, channel, and duration as `h:mm:ss` — read from the entry's own `meta.json`
(the library layout every reader consumes; nothing is re-derived). It prints before
the wiki hand-off note, so the shape of a finished add is: the pipeline's stage
lines, then *what this was*, then *what continues without you*. Today the only line
naming the video is the one the user typed; the id-heavy progress serves the machine,
and the close-out serves the person who will read fifteen of these in a sweep and
needs to know which talk just landed where. For a collection, one close-out per
completed video, in sweep order — the sweep's existing summary line stays the
accounting of record.

**`add [--verbose]`.** The flag exists so SPEC-ingest-004's captured-by-default
fetcher can still be watched raw when the user wants the tool's own feed: `add`
passes it through to ingest's boundary whole, the way every routed flag travels
(LESSON-0003 — the cli does not know what the flag changes, only where it goes).
Without the flag nothing is passed and ingest's quiet default holds. The surface
contract's `add` row gains the flag; `MANUAL.md` says what it does in the add
section; nothing else on the surface moves.
