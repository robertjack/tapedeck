---
id: SPEC-wiki-010
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-003, SPEC-wiki-004, SPEC-ingest-003]
---
A staging directory is not a stranger, and `sync`'s skip note must stop saying it is.

SPEC-wiki-003's selection passes over everything under `library/` it cannot file and notes
each one on stderr — the discipline that makes convergence reachable. One of those notes is
wrong. A directory named `.fetching-<id>-<random>` is ingest's download staging area
(SPEC-ingest-003), and both this component and cli described it identically as *"not a
video id — skipped, it is not tapedeck's"*. On 2026-08-16 a reader following that sentence
recommended `rm -rf` on a directory with a live `yt-dlp` inside it. The library survived
because a sandbox refused the command, which is not a control anybody designed.

So: when selection meets a name that is not a video id, it asks ingest whether the name is
a staging directory of ours (`ingest.staging`) rather than concluding from the name itself,
and the note it prints for one says so. The wording is this component's to choose and the
clause pins only the falsehood it must not contain: a staging directory may not be
described as foreign, not tapedeck's, or a stray. It belongs to a download of a known
video, and a reader deciding whether to delete it is deciding about that download.

SPEC-wiki-003's own prose is amended for the same reason — it called these entries
"foreign", which is where the code's wording came from. Genuinely foreign entries still
exist and are still described that way; the point is that this is not one of them.

`lint` is deliberately untouched. Its `unfiled` check shares this selection walk
(SPEC-wiki-004) but passes it no note callback — a diagnosis that only reads reports its
findings as check rows and says nothing about what it stepped over — so `lint` never
described a staging directory in the first place and has no falsehood to correct. The two
share the selection rule, not the sentences, and that is the whole of the overlap here.
