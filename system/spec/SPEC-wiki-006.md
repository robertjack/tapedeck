---
id: SPEC-wiki-006
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-001, SPEC-wiki-002, SPEC-wiki-004, SPEC-ask-005, SPEC-core-004]
---
`tend [--yes]` turns the maintainer loose on the wiki as a whole and asks it what it sees.
Without `--yes` it reports and cannot change anything; with `--yes` it edits under
SPEC-wiki-002's gate. It is the gist's LLM lint written in tapedeck's idiom —
**probabilistic inside, deterministic at the edges** — and the edge here is stronger than
the gate's, because the reading mode's guarantee does not depend on the agent's
cooperation at all. It reaches the installed surface as `tapedeck wiki tend [--yes]`
through SPEC-cli-009's whole-group pass-through, with no clause and no code in cli.

It exists because **the gate judges one filing and nothing judges the accumulated whole**.
SPEC-wiki-002's gate is a moment: it decides whether the operation in front of it left the
wiki mechanically sound, and everything it accepts is sound the second it is committed.
SPEC-wiki-004 extended that judgment across time without extending its nature — `lint`
re-asks the gate's questions of a wiki nobody just wrote, and every question it asks is
still one a machine can settle by reading bytes. Neither of them can see that two notes
filed three months apart say opposite things; that a page rests on a claim a later video
retracted; that a concept the wiki names on nine pages has no page of its own; that two
notes obviously belong linked and no link exists; that a source page nothing points at is
the most interesting thing in the library. Those are readings, not checks, and
SPEC-wiki-004 left them here deliberately — `orphans` reports a count precisely because a
deterministic linter can find where the web stopped and cannot say whether it should have
continued. Answering that requires something that can read the prose, and the only thing
in this system that reads prose is an agent.

The seam is therefore **`[wiki].maintainer_command`, unchanged** (SPEC-core-004,
SPEC-wiki-002): the agent that writes this wiki is the agent that tends it. A second seam
would be a second voice — a tender configured apart from the maintainer would read the
brief the maintainer follows and answer to a different one, and the wiki would accumulate
in two registers. The brief that disciplines filing is exactly the discipline tending
needs, since tending is filing's judgment applied to what filing produced. What
distinguishes the two runs is the task on stdin, which names the mode; everything else
about the invocation is the one this component already has. The command is run as a shell
command with cwd set to the wiki directory and `TAPEDECK_HOME` and `TAPEDECK_WIKI` in its
environment. There is no `TAPEDECK_VIDEO_ID` and no `TAPEDECK_ARCHIVE_PAGE`: tend takes no
video id and is about no video, and a variable naming one would be a lie about the scope
of the run. An absent or empty seam exits 2 with a message that says which key is missing
and that it holds a shell command, in `file`'s words. A wiki that is not there exits 2
naming the path it looked for — `lint`'s rule rather than `file`'s, because `file` and
`sync` scaffold when they are about to write into a wiki and tend is a verb about an
existing wiki's contents, and a wiki with nothing in it has nothing to tend.

Report mode is the default and it is the mode most runs will use. The agent is told to
read the wiki and print what it found — contradictions between pages, claims a newer
source supersedes, concepts the pages keep mentioning without ever defining, cross-links
that should exist, orphans worth connecting, questions the material raises and nobody has
chased — as prose on stdout, which tapedeck relays as the command's own stdout without
summarizing, re-wording or re-counting it. The findings are for the user to read, in the
maintainer's voice, the way the wiki itself is.

Whatever is pending in the working tree when the run starts is committed as `user edits`
first, the way every operation on this wiki commits it (contracts/wiki-layout.md): the
discard below is unconditional and takes untracked files with it, so a note the user typed
this morning and has not committed would otherwise be destroyed by the one verb that
promised to change nothing. That commit holds the user's own writing and nothing else, and
it is the state the reset returns to.

Afterwards tapedeck **unconditionally** runs `git reset --hard` and `git clean -fd`. The
reset is the whole guarantee, and it is a reset rather than an instruction on purpose: an
agent told to be read-only is a hope, and a reset afterwards is a fact. That is the same
argument the acceptance gate already rests on — tapedeck does not review the maintainer's
judgment and does not ask it to behave, it decides mechanically what lands — carried one
step further, to a run where the answer is that nothing lands. So a report run is
incapable of changing the wiki no matter what the agent did while it was reading: pages it
rewrote out of helpfulness, scratch files it left behind, a `CLAUDE.md` it improved.
`git clean -fd` is as load-bearing here as it is in the rollback, since anything the agent
created is untracked and a reset alone would leave exactly it. There is no commit of the
tend and no log entry: the log is the chronology of accepted operations (SPEC-wiki-001),
and a run that accepted nothing and changed nothing is not an event in the wiki's
history, however much the user learned from it. A nonzero exit from the agent is a failed
run — exit 1, with the tree reset all the same, because a crashed reader's leftovers are no
more welcome than a successful one's. Otherwise exit 0, whatever the findings said; tend
reports on the wiki's health and is not itself a check that can fail on it.

`--yes` is consent to let the tender edit, and the operation it consents to is
**SPEC-wiki-002's, op for op**. Whatever is pending in the working tree is committed as
`user edits` first, so the hand-edits sitting uncommitted at the moment of the run are on
the far side of every undo, and that commit is the pre-run commit everything later refers
to. The maintainer runs. A nonzero exit rolls back to the pre-run commit and exits 1. What
it wrote is otherwise put through the whole gate of SPEC-wiki-002, entire and unweakened:
`CLAUDE.md` byte-identical to its pre-run content, every `[[wikilink]]` in every page
resolving by the layout contract's rule, every deep link in every page verified through
ask's published boundary — one page's text per invocation, without `--require-citation`,
through `$TAPEDECK_ASK_CMD` when that variable is set and `<current python> -m ask`
otherwise — `index.md` linking every page in the wiki except the three pinned files, and
`log.md` still beginning with exactly its pre-run bytes and grown by at least one
well-formed entry, here `## [YYYY-MM-DD] tend | <subject>`. Reusing the file operation's
order and gate is not economy; it is the point. A verb that let an agent edit the wiki
under weaker terms than filing does would be a way to get unreviewed prose in by asking
for a tidy-up instead of a page, and the whole-wiki gate is already the right shape for a
whole-wiki edit — it was never a check on the diff. The one check of `file`'s that cannot
come along is its filing marker: that `sources/<id>.md` exists and cites its own recording
is a claim about the video just filed, and tend files no video and is handed no id. What
stands in its place is the rule below, which is the same concern read the other way round —
`file` asks that the marker appear, tend asks that no marker disappear.

One rule is tend's own, and it is the only thing this spec adds to the gate: **no page
under `sources/` may be deleted or renamed away**. Filed-state is not bookkeeping the wiki
keeps beside its content, it is SPEC-wiki-001's marker and `sync`'s entire contract — the
page's existence is the answer to "has this video been filed", which is why there is no
manifest to disagree with. A tender that merged two source pages into one, or retired a
page it judged thin, would silently un-file a video, and the next `sync` would notice a
video with no page and refile it, spending a maintainer run to recreate what a maintainer
just decided to remove. The wiki would oscillate, and nothing in it would be wrong enough
for any existing check to say so. The gate therefore rejects the operation naming every
`sources/<id>.md` that went missing, by that path, in the same terms as its other
violations, so the user learns which video lost its marker rather than that something was
deleted.

`notes/` carries no such protection, and the asymmetry is the design. Notes may be
created, rewritten, split, merged and deleted freely — reshaping the prose layer is what
tending *is*, and a tend that could only add would silt the wiki up with the
near-duplicates it was called in to resolve. Nothing downstream reads a note's existence as a
fact about the library; the notes tree is the user's and the maintainer's thinking, and
thinking is allowed to change its mind. Source pages are load-bearing state wearing the
same clothes as prose, and this is the one place that difference has to be enforced rather
than described. The user's protection against a tend they dislike is the one every wiki
operation offers: it is a commit, and the wiki they had is one `git revert` away.

A clean gate is `git add -A` and a commit named `wiki tend`, exit 0. Any violation is
`git reset --hard` and `git clean -fd` back to the pre-run commit, every violation on
stderr, exit 1 — each check independent and every failure reported, so one rejected tend
tells the user everything wrong with what the agent produced rather than the first thing
wrong. A rejected tend costs a maintainer run and leaves the wiki exactly as it was,
user edits included, which is the trade SPEC-wiki-002 already made and the reason its
rollback goes to the pre-run commit rather than the one before it.

What tend does not do bounds it. It never files a video: an unfiled video is `sync`'s
work, and a tender that noticed one and wrote its page would be filing without the archive
page a filing reads from and without the marker's operation ever having run. It never
scaffolds — a wiki is a prerequisite here, not an outcome. It reads no citation grammar of
its own and grows no second wikilink resolver; the gate it reuses consumes ask and the
layout contract exactly as it always did (LESSON-0003). And its findings in report mode
are **prose for the user, not machinery**: nothing parses them, nothing acts on them, no
exit code encodes them, and there is no `--json`, because the whole value of an agent
reading the wiki is the part a schema would have to throw away. Turning a finding back
into the wiki is what `--yes` is for.
