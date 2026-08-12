---
id: SPEC-ask-001
type: requirement
component: ask
status: active
depends: [SPEC-index-002, SPEC-core-004]
---
`ask <question>` retrieves the top-k chunks via the index (default 8, `-k` to adjust),
assembles a prompt containing the question and the numbered source excerpts, and
invokes the configured answerer with that prompt on stdin. The output follows
`system/contracts/ask-citations.md`: answer prose with `[n]` markers, then a Sources
section assembled by tapedeck (never by the LLM) from the actually retrieved chunks.
If retrieval returns nothing, ask exits 1 with "no sources in the library for this
question" and the answerer is never invoked.
