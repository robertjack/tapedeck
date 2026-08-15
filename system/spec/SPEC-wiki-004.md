---
id: SPEC-wiki-004
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-001, SPEC-wiki-002, SPEC-wiki-003, SPEC-ask-005]
---
`lint [--json]` diagnoses the wiki and changes nothing. It is `doctor`'s sibling one
layer up (SPEC-cli-007): where `doctor` says whether this installation can do the work,
`lint` says whether what the work produced still holds together — and it prints every
check it made, the passes included, because a report that lists only complaints cannot
tell "checked and fine" from "never looked".

It exists because the gate is a moment and the wiki is a life. SPEC-wiki-002's gate
judges one operation as it lands, and everything it accepts is sound the second it is
committed; nothing gates what happens next. The user renames a note in Obsidian, deletes
a page they thought was redundant, edits a source page's prose and takes its deep link
with it, or reclaims a video with `rm` and leaves the page that read it standing. Every
one of those is legitimate — the wiki is co-authored by design (contracts/wiki-layout.md)
— and every one of them can leave the wiki saying something that is no longer true.
`lint` is how the user asks the gate's questions of a wiki nobody just wrote.

Read-only is the whole discipline, and it is stricter than "does not write pages". `lint`
runs no maintainer, makes no commit, touches the network never, and writes nothing under
`wiki/` or anywhere else. It does not commit pending user edits: `file` does that because
it is about to risk work that a rollback must not take with it, and `lint` risks nothing,
so committing here would be a diagnosis quietly changing the thing it was asked to
describe. It therefore reads the working tree exactly as it stands, uncommitted hand
edits included, which is the wiki the user is actually looking at. It needs no maintainer
seam either — a wiki can be linted on a machine with no agent configured at all — and it
resolves the library and the wiki exactly as `file` does. A wiki that is not there exits
2, naming the path it looked for: `file` and `sync` scaffold because they are about to
write, and a diagnosis that scaffolds what it was asked to diagnose has answered its own
question with its own handiwork.

The report is one aligned line per check — the check's name, its status, and a short
detail — with the status beginning at the same column on every line so the report skims
as a column. A status is `pass`, `fail`, or `info`, and `info` belongs to the two checks
that only ever report: `unfiled` and `orphans` carry it whether or not they found anything
to say, because a count of nothing is still information rather than a thing that passed.
The detail names the thing that decided it: the page, the target that dead-ends, the id
whose video is gone. A check that says only `fail` costs the user a second run to learn
what everyone already knew, which is the same rule the gate follows when it reports
violations.

The checks are emitted in a fixed order and every one of them always appears:
`wikilinks`, `citations`, `index`, `log`, `sources`, `filed`, `unfiled`, `orphans`.

`wikilinks` asks that every `[[link]]` in every page resolve, by the layout contract's
rule and no other — the target is the text before the first `|`, matched case-sensitively
against page basenames with `.md` stripped, satisfied by any page anywhere under `wiki/`.
A dangling link is a page the writer believed existed, and it is the one defect nothing
reading the wiki afterwards can route around.

`citations` asks that every page's deep links still name a real video at a real
timestamp, and it decides that by invoking ask's published verification boundary
(SPEC-ask-005) exactly as the gate does: one page's text per invocation, without
`--require-citation` because a page that cites nothing has made no claim, through
`$TAPEDECK_ASK_CMD` when that variable is set and `<current python> -m ask` otherwise.
What ask says about a bad link is what reaches the user, relayed rather than replaced by
a message of this component's own. Citation grammar is ask's vocabulary (LESSON-0003) and
a second reading of it living in a linter would be the defect whether or not it currently
agrees — a linter that disagreed with the gate about a link would be worse than no linter,
because it would send the user to fix a page the gate is perfectly happy with.

`index` checks the catalog in **both directions**: every page in the wiki except the three
pinned files is linked from `index.md`, and every link in `index.md` points at a page that
exists. The gate checks only the first, and it is right to — the failure a maintainer
produces is a page it forgot to catalog. The failure a person produces is the other one:
they delete or rename a page and the line describing it stays behind, and the catalog now
promises a reader something the wiki cannot deliver. `index.md` is the entry point for a
human opening the directory, so a lie in it is read before anything else is.

`log` asks that every heading in `log.md` that opens like an entry — every line beginning
`## [` — actually match the pinned grammar `## [YYYY-MM-DD] <op> | <subject>`. The gate
checks the chronology as a byte-prefix and a fresh entry, both of which are claims about a
before and an after; a standing wiki has no before, so what is checkable here is the shape
of what is written. The shape is what keeps the log greppable without tooling, and a
heading that drifted out of it is an event the chronology can no longer be read to
contain.

`sources` asks that every source page still carry at least one deep link to its own video.
This is the gate's rule about the page it just accepted, re-asked of every page ever
accepted, because the anchor is what makes the page a reading of a recording rather than
a summary of a memory — and prose survives edits that its citations do not.

`filed` asks that every source page's video is still in the library. `rm` reclaims videos
and knows nothing about the wiki, by design: the wiki is the one layer SPEC-core-002 does
not govern, and it is not thrown away because the library shrank. But a page describing a
video the library no longer holds is knowledge left dangling — its deep links point where
nothing is, and nothing downstream can check it any more — so the check names which video,
every time, because that is the whole content of the finding. "Still in the library" means
the entry, not the media: a video reclaimed by `rm --media-only` (SPEC-cli-002) was
explicitly kept as knowledge, its metadata and archive page intact, and its wiki page
stands on the same footing — `filed` fails only when the entry itself is gone. What to do about it is the
user's call: re-`add` the video, or delete the page and let the log remember it happened.
A read-only verb states the fact and leaves the decision where it belongs.

`unfiled` reports the library videos eligible for filing that have no page yet, and it is
`info` — it never fails and never touches the exit code. Eligibility is `sync`'s
(SPEC-wiki-003): a well-formed id by ingest's grammar, media present by ingest's rule, an
archive page rendered. Those rules are ingest's vocabulary and are consumed here, not
re-derived. The status is information because the wiki is accumulated by choice and is not
a mirror of the library — a user may deliberately never file a video, and a library that
grew this morning is not a wiki that broke this morning. Filing them is `sync`'s job and
saying so is this line's job; failing on it would make `lint` red for a wiki whose only
sin is being younger than the library.

`orphans` reports pages that no other page wikilinks to, and it is `info` for a different
reason. Such a page is not unreachable — the `index` check already guarantees the catalog
carries it — it is merely unconnected, and a note written ten minutes ago that nothing
points at yet is an ordinary moment in writing rather than a fault. The catalog does not
count as an incoming link for this check: `index.md` links every page by rule, so counting
it would mean no page is ever an orphan and the line would report nothing at all. What it
reports is where the wiki has stopped being a web, which is a thing the user may want to
know and never a thing tapedeck should refuse to proceed over.

Exit 0 when no check failed and 1 otherwise; `info` results never make it 1, so a wiki
that is sound but incomplete is sound. `--json` emits the same checks in the same order as
`[{check, status, detail}]`, so the report a person skims and the report a script reads
can never disagree about what was checked. Piped output carries no escape sequences.
