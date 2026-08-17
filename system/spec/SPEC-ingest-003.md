---
id: SPEC-ingest-003
type: requirement
component: ingest
status: active
depends: [SPEC-ingest-001, SPEC-core-001]
---
ingest publishes what a staging directory is, because ingest is what creates them.

`library/.fetching-<video-id>-<random>/` is where a download happens before it is renamed
into place (SPEC-ingest-001's atomic install). Until now that shape existed only inside
`fetch.py`, and every other component that walks `library/` met these directories with no
published rule to consult. Both of them — cli's sweeps and wiki's selection — invented
the same description independently, and both got it wrong in the same words: *"not a
video id — skipped, it is not tapedeck's"*. It is tapedeck's. On 2026-08-16 that sentence
led a reader to recommend deleting one that had a live `yt-dlp` running inside it.

So the boundary grows a published question: **given a name in `library/`, is this a
staging directory, and if so which video is it fetching?** It is exported as
`ingest.staging(name)`, returning the video id when the name is one of ours and `None`
otherwise, alongside `VIDEO_ID` and `has_video` — the same kind of thing, vocabulary the
system shares rather than re-derives (LESSON-0003). It answers from the name alone, so a
caller can ask about a directory entry without touching the filesystem.

The name is pinned here rather than left to the implementation because three components
have to agree on it, and each is regenerated without seeing the others' source. A clause
that said only "publish a predicate" would get three predicates.

Note honestly what the durable evals can and cannot hold. They drive component boundaries
as subprocesses, never imports (SPEC-core-002), so no eval can assert that cli and wiki
*call* this function rather than matching the prefix themselves. What the evals pin is the
observable consequence — the sentence each component prints about a staging directory
(SPEC-cli-010, SPEC-wiki-010). The single-owner rule is a contract statement enforced in
review, and this paragraph exists so nobody later mistakes a green suite for proof of it.

A consumer can then distinguish the three cases a walk actually meets: an entry whose
name is a video id, a staging directory of ours, and something genuinely not ours. Only
the third deserves to be called a stranger. What a consumer *says* about the second is its
own business (cli and wiki report to different audiences), but neither may claim it is
foreign, and neither may re-derive the prefix to find out.

Whether a given staging directory is a **live** fetch or an abandoned one is deliberately
not part of this: that is a question about a process, not a name, and a component that
guessed would be wrong exactly when it mattered. The published answer stops at "this is
ours, and it belongs to a fetch of `<id>`" — which is enough for a reader to know that
deleting it is a decision about a download rather than a tidy-up.
