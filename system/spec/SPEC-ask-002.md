---
id: SPEC-ask-002
type: constraint
component: ask
status: active
depends: [SPEC-ask-001]
---
The answerer works only from the library. The assembled prompt instructs the model to
answer strictly from the provided source excerpts, to cite with the given `[n]`
markers, and to reply "not in the library" when the sources are insufficient — the
probabilistic step is quarantined behind deterministic retrieval and deterministic
citation assembly, and the prompt text itself is part of this component's testable
surface.
