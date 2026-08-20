---
id: SPEC-wiki-002
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-001, SPEC-ask-005, SPEC-core-004]
---
`file <id>` files one library video into the wiki. The writing is done by a maintainer —
a configured agent that reads the brief, reads the archive page, and edits the wiki as it
sees fit — and tapedeck does not review its prose, its taxonomy, or its judgment about
what deserves a note. It reviews the result. **The design is probabilistic inside and
deterministic at the edges**: the maintainer may write anything, and the gate decides what
lands. Everything below is the edge.

Nothing probabilistic runs until the cheap questions are settled. `<id>` must be a
well-formed video id present in the library; malformed or unknown exits 2 before the seam
is read. If `archive/<id>.md` is missing the video is in the library but not yet rendered,
which is an operation failure, not a usage error: exit 1, naming the page and the `add`
that produces it. If `sources/<id>.md` already exists the video is filed and `file` is
**idempotent** — it notes the skip on stderr and exits 0, having changed nothing, so
filing a whole library is a loop the user can re-run without thinking about where it
stopped.

The maintainer is a seam like every other (SPEC-core-004): `[wiki].maintainer_command` in
`$TAPEDECK_HOME/config.toml`, absent or empty exits 2 with a message that says which key
is missing and that it holds a shell command. It is run as a shell command with cwd set to
the wiki directory, the task instructions on stdin, and four variables in its environment:
`TAPEDECK_HOME`, `TAPEDECK_WIKI` (the wiki directory), `TAPEDECK_VIDEO_ID`, and
`TAPEDECK_ARCHIVE_PAGE` (the absolute path of `archive/<id>.md`). The published default,
which cli scaffolds into `config.toml` with the rest of the commented defaults, is
`claude -p --permission-mode acceptEdits --allowedTools "Read,Grep,Glob,Write,Edit"` — an
agent that can read the library and write the wiki, and nothing else. A user who prefers
another agent, or a script, edits the line.

The operation runs in a fixed order, and every step exists because of the one after it.
The wiki is scaffolded if it is absent (SPEC-wiki-001). Whatever is pending in its working
tree is then committed as a `user edits` commit: the user's own hand-edits are theirs and
must survive a rollback that the maintainer's work triggers, so they are made into history
before anything else can happen, and that commit is the pre-run commit every later step
refers to. The maintainer runs next, and a nonzero exit is a failed operation: the wiki
goes back to the pre-run commit and the command exits 1, because whatever a crashed agent
left half-written is not the wiki's problem. What it wrote is otherwise verified against
the gate below. On a clean gate, `git add -A` and a commit named `wiki file <id>`, exit 0;
on any violation, back to the pre-run commit again and exit 1 with every violation on
stderr. Going back means `git reset --hard` **and** `git clean -fd` on both paths — the
pages a maintainer created are untracked, so a reset alone leaves exactly the half-written
work the rollback exists to remove — and it means the pre-run commit rather than the one
before it, so the user's hand-edits are on the far side of every undo.

One operation holds the wiki at a time (LESSON-0004). Before anything above — before even
the `user edits` commit — the operation takes an exclusive advisory lock on a file inside
the wiki's own git directory, where no reset or clean ever reaches and where the operating
system releases it with the process that held it, so a crashed operation cannot leave a
lock behind to clean up. A second mutating operation that finds the lock held does not
wait and does not interleave: it exits 1 at once, saying another wiki operation is
running, because the alternative is not hypothetical — two concurrent filings on a live
library left one committing the other's half-written pages as `user edits`. The refusal
costs nothing a sweep cannot recover: filing is idempotent and the next `sync` converges.
Read-only diagnosis takes no lock and never waits — `lint` and a dry-run `sync` may run
mid-operation and merely describe a moment in flight. Every operation that writes the
wiki — a filing, a sweep's filings, a rebuild, a tend in either mode — holds the lock for
exactly the span from before its pre-run commit to its commit or its rollback.

The gate verifies the **whole wiki**, not the diff. A maintainer edits wherever the brief
sends it, and a filing that fixes its own page while breaking a link three notes away is
the failure this catches. Each check is independent and every failure is reported, so one
run tells the user everything wrong rather than the first thing wrong; and each violation
names the thing that broke it — the file that changed, the target that dead-ends, the page
the catalog forgot — because a rejection nobody can act on costs a maintainer run and buys
nothing.

`CLAUDE.md` must be byte-identical to its content at the pre-run commit. The brief is the
user's instructions to the maintainer, and an agent that may rewrite its own instructions
has none; any change at all, including one the maintainer believes is an improvement,
fails the gate. `sources/<id>.md` must exist and must carry at least one deep link to
`<id>` itself — it is the filed-state marker of SPEC-wiki-001 and it must be anchored to
its own recording. The shape of that link is the library layout's one deep-link rule,
which is the video's *own* address: a YouTube video is cited as `watch?v=<id>`, a local
one by its `file://` path (SPEC-ingest-005). This component reads that rule rather than
restating a host, because a gate that only recognizes YouTube would reject every filing
of a video that came off disk — and the task the maintainer is handed quotes the same
address form for the same reason, so it never has to invent one. Every `[[wikilink]]` in every page must resolve: the target is the text
before any `|` alias, matched case-sensitively against the basename-without-`.md` of some
page anywhere under `wiki/`, and a wiki whose links dead-end is a wiki nobody trusts on the
second read. Every deep link in every page, of either form, must verify against the library — the
video exists, the timestamp is in bounds — decided by invoking ask's published boundary,
one page's text per invocation, without `--require-citation`, because a note that cites
nothing is allowed and a note that cites something false is not; what ask says about a bad
link is what reaches the user, relayed rather than replaced by a message of this
component's own. `index.md` must link every page in the wiki except the three pinned files,
since a catalog that silently omits a page is worse than no catalog. And `log.md` must
still begin with exactly its pre-run content and must have gained at least one well-formed
entry (`## [YYYY-MM-DD] <op> | <subject>`) — append-only checked as a byte-prefix, which is
the only reading of it that an agent cannot argue with.

Two of those checks rest on vocabulary wiki does not own, and wiki consumes both rather
than writing its own copy (LESSON-0003). Whether `<id>` is well-formed is ingest's
definition of the id grammar. Whether a deep link is real — where a URL ends when
sentence punctuation follows it, what an unknown duration waives — is ask's, settled in
contracts/ask-citations.md and published as `ask verify` by SPEC-ask-005 precisely so this
component can ask instead of re-deriving. wiki invokes it as `$TAPEDECK_ASK_CMD` when that
variable is set and as `<current python> -m ask` otherwise, the same override the evals
document; that is the seam through which a fake ask is injected, and it is the reason a
change to the citation rules changes the gate with no clause and no code here. A second
regex for YouTube links living in this component would be the defect whether or not it
currently agrees.
