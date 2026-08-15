---
id: LESSON-0005
components: [index, cli]
source: incident
evidence: 2026-08-15 — the deletion-test rebuild (~/dev/personal/tapedeck_rebuild) regenerated this repo from its durable layer alone with a different model; the regenerated index legitimately omitted the PRAGMA user_version guard (no clause or index eval demanded it — the rule lived only in src/ plus a precondition in ask's suite), and the cli eval suite scored 69/73 against the deployed PATH binary while src/cli did not exist
status: active
---
Two ways knowledge silently escapes the durable layer, both found by rebuilding from
it: an implementation behavior no clause states and no owning-component eval demands
survives only until the next regeneration (SPEC-core-001's violation in its natural
habitat — the guard existed, worked, and was written nowhere); and an eval that
resolves its subject from the environment (a PATH binary, an installed package)
attests whatever is installed, not what the repo produces. Evals must drive the
artifact the repo builds, from the repo, and every cross-component precondition
belongs in the suite of the component that owes the behavior.
