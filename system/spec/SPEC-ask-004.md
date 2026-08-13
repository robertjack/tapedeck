---
id: SPEC-ask-004
type: requirement
component: ask
status: active
depends: [SPEC-ask-001, SPEC-index-001, SPEC-index-003]
---
`ask --fast` reads `tapedeck.db` itself rather than shelling out to the index, and
must hold that database to the same shape gate the index holds it to: a file whose
schema version or whose tokenizer is not the one this build searches under is not an
index ask may answer from. Such a database fails the command with exit 1 naming the
same reindex hint a missing database gets, and the answerer is never invoked — the
shape is settled before anything probabilistic runs. Answering anyway is the failure
this forbids: a library where `tapedeck search` refuses and `ask --fast` quietly
answers from pre-migration rows gives two accounts of itself, and the wrong one is
the one that sounds authoritative.
