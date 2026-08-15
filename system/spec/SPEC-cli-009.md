---
id: SPEC-cli-009
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-cli-002, SPEC-cli-003, SPEC-cli-005, SPEC-wiki-002, SPEC-wiki-003]
---
`wiki` is a verb group rather than a verb. `tapedeck wiki file <id>`,
`tapedeck wiki sync [--dry-run]`, `tapedeck wiki lint [--json]` and
`tapedeck wiki rebuild [--yes]` are handed over **whole** to `python -m wiki`: everything
after the word `wiki` goes to the child untouched, the child's stdout and stderr are the
user's on the same streams as they are produced, and the child's exit code is tapedeck's.
The cli routes and does nothing else. It does not know what `--dry-run` prints, does not
decide whether `<id>` is well-formed, does not learn what the wiki's filed-state marker
is, and does not summarize, re-word or re-count anything the component said.

That is LESSON-0003 written as a routing rule. The alternative — restating each wiki verb
and each of its flags in the cli's own argparse — would put a second copy of the wiki's
surface in the component that merely launches it, and the copies would drift the way every
hand-copied rule in this system has drifted: usage text describing a flag that moved,
validation rejecting an id the component would have accepted, a `--json` added one layer
up and invisible from the installed tool. Because the group passes through whole, the wiki's
own specs (SPEC-wiki-001 through SPEC-wiki-005) govern every behavior behind it, and a verb
or flag they add reaches the installed `tapedeck` with no clause and no code here.
SPEC-cli-001's exact verb list gains `wiki`; the surface contract gains one row for the
group, not four.

Auto-filing is the second half of the round, and it lives inside `add`. After **each**
video's pipeline succeeds — ingest, transcribe, archive, index, the whole four-stage chain
for that one id — the cli runs the wiki filing for that id, before it moves to the next
video, in the same order the sweep of SPEC-cli-003 runs. The filing is `wiki file <id>`
itself, invoked at the component's boundary the way every stage of the chain is invoked:
the epilogue is a call, not a second filing path, so the maintainer, the acceptance gate,
the rollback and the idempotent skip of an already-filed video are SPEC-wiki-002's and
this clause adds none of its own (LESSON-0003). Filing as each video completes
rather than in one pass at the end is what makes an interrupted sweep of a channel leave
behind a wiki that matches the part of the library it managed to build, and it is what
lets the maintainer read pages filed earlier in the same sweep, which is the accumulation
SPEC-wiki-003's ordering exists to produce.

The epilogue is **best-effort, and that is the specification**. A filing that fails — a
rejected gate, a crashed maintainer, a `[wiki].maintainer_command` that is absent or
resolves to nothing — is one note on stderr and nothing more. It never changes `add`'s exit
code, never appears as a `failed` count in the collection summary, and never stops the
sweep. The note names the video it was filing and says it was the wiki filing that
failed, and where the seam is the reason it names `[wiki].maintainer_command`, because a
line saying only that something went wrong sends the user searching a library that is in
fact complete. Nothing about the epilogue reaches stdout at all, filed or not: `add`'s
stdout is the stdout it printed before there was a wiki, which is what lets the summary
line go on meaning exactly what it meant. A knowledge layer must not make the archive
pipeline fragile: the video is downloaded, transcribed, rendered and indexed, which is
what the user asked `add` for and what cost them the bandwidth and the minutes, and a
wiki page that did not get written is a `tapedeck wiki sync` away at any later moment. Filing is recoverable; a red `add` that
sends the user hunting through a completed library for what actually broke is not. Nothing
about the epilogue can damage the library either, since everything the maintainer and its
gate touch is under `wiki/` and rolls back there.

Whether the epilogue runs at all is `[wiki].auto`, and **an absent key reads true**. The
first-run `config.toml` scaffold gains a `[wiki]` section beside the others in its existing
commented style: `auto = true`, and `maintainer_command` set to SPEC-wiki-002's published
default verbatim,
`claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"`, so
the seam and the switch are visible and editable on the first day like every other default
(SPEC-core-004). The absent key must read the same way the scaffold writes it, because the
alternative is two defaults for one question — the shipped file saying `true` while a
config written before this clause silently means `false` — and a user would then get
different behavior from the same tool depending on the age of a file they never edited.
There is one default, the scaffold writes it down, and the code agrees with what it wrote.
Turning the epilogue off is `auto = false`, an edit the user made on purpose, and it means
`add` never touches the wiki: no maintainer, no note, no mention of a wiki at all, since
silence is the whole content of the request.

`rm` gains one sentence of its own. When `rm <id>` removes a video — full removal, not
`--media-only` — and `wiki/sources/<id>.md` exists, the cli prints one note on stderr
saying the wiki still holds a page for this video and that `tapedeck wiki lint` will name
it. It deletes nothing under `wiki/` and edits nothing there: the wiki is accumulated,
user-owned, versioned state (SPEC-wiki-001), `rm` is a library verb, and a page whose video
is gone is a decision for the person who wrote it — re-add the video, or delete the page —
exactly as SPEC-wiki-004's `filed` check leaves it. Asking whether the file exists is not
the cli re-deriving the wiki's vocabulary: `contracts/wiki-layout.md` blesses that
existence check as *the* answer to "is this video filed", which is the point of storing the
state as a filename. `--media-only` prints no such note, because that removal deliberately
keeps the knowledge (SPEC-cli-002) and the page still stands on the entry it describes,
which is precisely why `filed` passes it. `rm`'s exit codes and everything else about its
behavior are unchanged.

`help wiki` prints the verb group's usage followed by a worked example, through
SPEC-cli-005's existing `help <verb>` mechanism and with no new machinery. The
no-argument tour's everyday-verb list is unchanged: the wiki is a layer a user grows into,
not one of the handful of verbs a stranger needs on the first screen. `MANUAL.md` gains a
wiki section — the four verbs, the brief at `wiki/CLAUDE.md` and that it is the user's to
rewrite, auto-filing and the one line that turns it off, Obsidian or any markdown editor as
the reading surface, and `lint` and `rebuild` as the maintenance pair — so the rule that
every verb on the surface appears in the manual (SPEC-cli-005) holds with the new row. The
machine on which auto-filing quietly did nothing has somewhere to ask why: `doctor` reports
`wiki.maintainer_command` as an optional check (SPEC-cli-007), and `setup` reports it
because `setup` reports what `doctor` reports. Exit codes are otherwise untouched — the
pass-through carries the wiki component's, and nothing else on the surface changes.
