---
id: SPEC-wiki-008
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-wiki-003, SPEC-wiki-006, SPEC-wiki-007]
---
`index.md` and `log.md` are bookkeeping, and bookkeeping is not probabilistic. tapedeck
maintains both from what it already knows; the maintainer is no longer asked to, and its
task no longer mentions them.

The cost of asking was measured on the user's own wiki at ten filed videos. `log.md` had
reached 97KB — eleven entries, the most recent one 14KB — and a maintainer restricted to
`Read,Grep,Glob,Write,Edit` cannot append a line to a file without reading all of it
first, so every filing spent roughly 24,000 input tokens re-reading a chronology that
tells it nothing about the video it was handed, and then wrote the file back. `index.md`
cost another 4,000 the same way. Both grow with every operation, and neither is a
judgment call: the date is tapedeck's, the operation is tapedeck's, the set of pages
needing a catalog line is a directory listing. **The wiki is probabilistic inside and
deterministic at the edges (SPEC-wiki-002); the bookkeeping is an edge, and paying agent
prices for it was the defect.** Left alone it also ends the component: at forty videos
the chronology alone exceeds what a filing can hold in context beside a transcript, and
filings stop succeeding rather than merely costing.

So: after the maintainer exits and **before the gate judges the result**, tapedeck
reconciles both files. The order is not incidental — the gate must judge the state that
is actually committed, and a rejection must roll back tapedeck's reconciliation along
with everything else, or a refused operation leaves its bookkeeping behind.

The catalog is reconciled by **appending the lines that are missing, never by
regenerating the file**. Which pages are grouped where, in what order, under which
headings, and whether a line carries a summary at all remain the brief's business
(system/contracts/wiki-layout.md) and a rebuild of the file would quietly overrule the
user every time it ran. A page that has no line gets one, linking its path, annotated
with its own opening heading where it has one; a page that already has a line is left
exactly as it is.

The chronology gains **exactly one entry per accepted operation**, in the pinned shape,
and tapedeck is what guarantees the count. Where the agent appended a well-formed entry
of its own, that entry stands and tapedeck adds nothing — a maintainer already
configured to write its own chronology is not doing anything wrong, and an operation
that produced two entries would be a worse record than one that produced none. Where the
agent appended none — which is now the ordinary case, since nothing asks it to — tapedeck
appends one: the `<op>`, the date and **the subject** are its own, and the maintainer's
product is the prose beneath it. An agent that narrated nothing at all still gets an
entry, because the operation still happened; a silent run is not a gap in the history.

**Amended again 2026-08-17, after a `tend` read the entries this clause produced.** The
first version made the *subject* the maintainer's product too, and the wiki's own brief
documents the heading as `## [YYYY-MM-DD] file | <video-id>`. Eleven entries written by
hand followed that rule; the two written by this clause did not — one of them reads
`## [2026-08-16] file | Filed. Here's what landed. **`sources/whcfSGN6CAU.md`**`, having
swallowed a paragraph of body prose into the heading field. The clause contradicted the
contract it was amending, and nothing caught it: the eval asked only that the subject be
non-empty, which a swallowed paragraph satisfies perfectly.

So the subject is tapedeck's, and it is what the brief already documents — the video id
for a filing, and for an operation with no single subject a short fixed label naming what
happened. It is one line and it carries no markdown, because a heading is an index entry
and `grep "^## \["` is how this log is meant to be read. The product keeps its place in
the body, entire and unedited.

The entry tapedeck writes also carries what the run cost. These are the only numbers
that say whether the wiki is getting more expensive to keep — the question this clause
exists to answer, and one that until now could only be reconstructed from commit
timestamps after the fact. tapedeck records them when the stream carries them and omits
them silently when it does not: a maintainer configured without `--output-format
stream-json` is a supported maintainer (SPEC-core-004), and its entry is the same
well-formed entry minus those figures, never a malformed one and never a row of zeroes.

**Amended 2026-08-16, after the first two filings measured with it.** The first version
of this clause recorded the result event's `input_tokens` as the run's input, and the
entries it wrote read `118 in / 69311 out tokens · $9.16` and `100 in / 67117 out tokens
· $8.33`. A hundred input tokens for a run that read a transcript is obvious nonsense:
`input_tokens` is only the *uncached remainder*, and the run's actual input is
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. The figure was
wrong by four orders of magnitude, in the one direction that mattered — those two runs
cost $9.16 and $8.33, of which roughly four fifths was input processing, and the entry
attributed almost none of it. A measurement that cannot see the dominant cost cannot
answer the question it was added for.

So the entry records, from the result event and the run's `init` event: the **total input
tokens** (that sum), **how many of them were served from cache** — because a filing's
cost is context size multiplied by turn count, and the cache-read share is what makes
that visible — the **output tokens**, the **duration in whole seconds**, the **price in
USD**, and the **model that answered**. Every count is a plain integer with no thousands
separators, for the same reason the chronology's heading shape is fixed: the log is meant
to be read with `grep` and summed with `awk`, by someone who has not installed anything.

**And it reads as prose, because the chronology is prose.** The first version rendered
`980s · 118 in / 69311 out tokens · $9.16` — a status line, correct and machine-friendly,
dropped unremarked into a file whose every other sentence is careful. The same `tend` that
found the broken heading noted the irony precisely: this is a wiki whose most-edited note
is `nobody-prices-it`, thirteen filings about nobody costing agent work, and the first
cost figure ever to appear in it arrived as leaked telemetry. So the figures go into a
sentence that says what they are. They stay greppable — plain integers, one line, the same
words every time — and they stop reading like a tool talking to itself.

This is the one requirement here no eval can hold. "Reads as prose" is a judgment, and an
eval that pinned particular words would freeze a wording the brief is entitled to dislike.
The evals pin the figures and the shape; the voice is checked by reading it.

The scaffolded brief changes with the task, and for the same reason. `CLAUDE.md` is
written once and is the user's thereafter (SPEC-wiki-001), but the default tapedeck ships
currently lists the catalog and the chronology among the things an operation is checked
on — which is an instruction to go and maintain them, read by every maintainer on every
run of every fresh install. Wherever the default brief names `index.md` or `log.md` it
must now say that tapedeck keeps them, and it must stop listing them as work the
maintainer is judged on. A user who wants the old arrangement still has it: writing the
entry is permitted, and the brief is theirs to change back.

**The maintainer is told that its report becomes the record.** The same `tend` found an
entry whose own text reads "CLAUDE.md, `index.md` and `log.md` are untouched" — true when
the agent wrote it, false the moment tapedeck appended it to the chronology. That is not a
wording slip: *any* self-report placed into the file it describes can be falsified by the
placing, and the agent had no way to know where its words were going. So the task says so
— that what it reports becomes this operation's entry in the wiki's own chronology, and it
should be written as a record of what happened rather than as a message to whoever asked.

Note what this does not reintroduce: the task still never asks the maintainer to *maintain*
the chronology, and still does not name the file. Knowing your words become the record is
not the same instruction as "go and update the log", and the saving this clause exists for
is untouched.

**A run that changes nothing still costs something.** Attaching the figures to accepted
operations left one hole: `tend`'s report mode (SPEC-wiki-006) spends a full agent run,
writes no entry by design — the chronology records accepted operations, and a reading is
not one — and therefore recorded nothing at all. The first such run under this clause took
ten minutes and left no trace of its price in the one record built to answer whether this
wiki is getting more expensive. So a run whose result is discarded prints its cost on
stderr as it finishes, in the same words the entry would have used. It is a diagnostic
rather than history, and deliberately not persisted: a file to hold it would be a sixth
entry in a tree the layout contract pins at five, and inventing one to store a number is
worse than the number being ephemeral.

What does not change is as important. The gate's checks are untouched: the catalog must
still account for every page, the chronology must still be a byte-prefix of what it was,
and both are still checked over the whole wiki. They simply become invariants tapedeck
satisfies by construction rather than obligations an agent can fail — which is strictly
stronger, since the failure they used to catch cost a whole run to discover. The
maintainer is also still *permitted* to write either file. Forbidding it would be a
larger claim than this clause needs: an agent that writes its own entry is not doing
anything wrong, a `tend --yes` that regroups the catalog is doing exactly what that verb
is for (SPEC-wiki-006), and a rule against it would break every maintainer already
configured to do so. The saving comes from no longer *asking* — from the task, not from
the gate.
