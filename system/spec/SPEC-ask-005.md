---
id: SPEC-ask-005
type: requirement
component: ask
status: active
depends: [SPEC-ask-001, SPEC-ask-003]
---
`ask verify [--video <id>] [--require-citation]` takes text on stdin and reports whether
its citations hold: exit 0 when every deep link in the text checks out, exit 1 when any
does not, with each violation named on stderr so a caller can act on all of them at once
rather than one per run. The check applied is exactly the one SPEC-ask-001 already
applies to a librarian's answer — every deep link must name a video present in the
library, with a timestamp inside that video's duration — read exactly per
`contracts/ask-citations.md`, trailing sentence punctuation and the unknown-duration
waiver included. There is one reading of a citation in this system; this verb publishes
it, it does not add a second one. If the two ever disagree the verb is wrong, and an
eval that pins the same punctuation and `duration_s: 0` cases against both is what keeps
that honest.

Verification exists as a boundary because ask is not its only reader. The wiki component
must decide whether a page it just accepted cites the library truthfully, and the only
way for it to reach the same verdict ask reaches is to ask ask (LESSON-0003): citation
grammar, the bounds check and the punctuation rule are this component's vocabulary, and
a second correct-looking copy of them living in another component is the defect whether
or not it is currently right — both sides' evals stay green while the answers drift.
What was an internal step of one verb is therefore a verb of its own, reachable at
`python -m ask verify` like every other component boundary.

Two flags account for the ways a caller's text differs from a librarian's answer.
`--video <id>` tightens scope exactly as SPEC-ask-003 does — a link to any other video
is a violation even though that video is in the library — and an id not in the library
exits 2 before anything is read, naming the id it could not find, settled by the one
path lookup that question needs.
`--require-citation` restores the at-least-one-link rule that librarian mode enforces:
uncited text fails. It is opt-in rather than the default because the callers this verb
was published for verify pages, and a page with no deep link in it has made no claim to
check; an answer with none has dodged the question, which is why the mode that produces
answers keeps requiring one.

`verify` invokes no seam command and mutates nothing — no librarian, no answerer, no
index write, no library write. It reads the library and reports. A caller that runs it
inside its own accept-or-roll-back decision (wiki does) must be able to run it on
whatever text it holds, as often as it likes, without the run being a step that has to
be undone. ask's own modes are unchanged by this: librarian and fast mode verify what
they verified before, on the same failures, with the same exit codes.
