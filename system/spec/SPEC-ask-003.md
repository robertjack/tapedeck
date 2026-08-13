---
id: SPEC-ask-003
type: requirement
component: ask
status: active
depends: [SPEC-ask-001]
---
`ask --video <id> <question>` scopes both modes to a single library video. An id not
in the library exits 2 before any external invocation. In fast mode retrieval returns
only that video's chunks, and empty scoped retrieval refuses exactly like an empty
library. In librarian mode the question handed to the librarian names the scope — it
is told to answer only from that video's files — and citation verification tightens
to match: a deep link to any other video is a verification failure (exit 1), even if
that video is in the library. The cli passes `--video` through on `ask`.

Deciding whether a scope id names something is one question about one path — settle it
by asking whether `library/<id>` is there, not by enumerating and parsing the whole
library to see if the id turns up in the result. A library is a directory that grows
without bound; a check whose cost grows with it, run before every scoped question and
then again inside the mode, is a scan the answer never needed.
