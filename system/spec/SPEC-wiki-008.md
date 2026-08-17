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
appends one: the `<op>` and the date are its own, and the subject and the prose beneath
it are the maintainer's product, the text SPEC-wiki-007 already extracts from the run. An
agent that narrated nothing at all still gets an entry, because the operation still
happened; a silent run is not a gap in the history.

The entry tapedeck writes also carries what the run cost: **its duration in whole
seconds, its input and output token counts, and its price in USD**, as the result event
reports them. These are the only numbers that say whether the wiki is getting more
expensive to keep — the question this clause exists to answer, and one that until now
could only be reconstructed from commit timestamps after the fact. tapedeck records them
when the stream carries them and omits them silently when it does not: a maintainer
configured without `--output-format stream-json` is a supported maintainer
(SPEC-core-004), and its entry is the same well-formed entry minus those figures, never
a malformed one and never a row of zeroes.

The scaffolded brief changes with the task, and for the same reason. `CLAUDE.md` is
written once and is the user's thereafter (SPEC-wiki-001), but the default tapedeck ships
currently lists the catalog and the chronology among the things an operation is checked
on — which is an instruction to go and maintain them, read by every maintainer on every
run of every fresh install. Wherever the default brief names `index.md` or `log.md` it
must now say that tapedeck keeps them, and it must stop listing them as work the
maintainer is judged on. A user who wants the old arrangement still has it: writing the
entry is permitted, and the brief is theirs to change back.

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
