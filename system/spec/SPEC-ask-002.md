---
id: SPEC-ask-002
type: constraint
component: ask
status: active
depends: [SPEC-ask-001]
---
Both ask modes work only from the library; the probabilistic step is quarantined
behind deterministic checks. In fast mode, the assembled prompt instructs the model to
answer strictly from the provided source excerpts, to cite with the given `[n]`
markers, and to reply "not in the library" when the sources are insufficient — the
prompt text is part of this component's testable surface. In librarian mode, the same
grounding rules live in the library-home `CLAUDE.md` brief (scaffolded on first run by
the cli component), and the mechanical backstop is the post-hoc citation verification
of SPEC-ask-001: freedom to retrieve, no freedom to fabricate.
