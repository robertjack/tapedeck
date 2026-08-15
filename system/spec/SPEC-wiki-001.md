---
id: SPEC-wiki-001
type: requirement
component: wiki
status: active
depends: [SPEC-core-001, SPEC-core-004]
---
The wiki is where a library stops being a pile of videos and becomes something the user
knows. The four-stage chain ends at an index that can answer questions about what was
said; the wiki holds what the user made of it — the connections, the naming, the second
thought a month later — and it accumulates one filing at a time. It lives at
`$TAPEDECK_HOME/wiki/`, beside `library/` and `archive/`, because it is about this
library and travels with it, and wiki is its sole writer under SPEC-core-001.

`wiki/` is **its own git repository**, initialized by tapedeck and not nested inside any
other: not the code repo, which holds no user data, and not the library home, which holds
gigabytes of video that nothing should be asked to version. Every accepted operation is a
commit, so history is the wiki's memory and its recovery mechanism at once — the user can
read what changed, revert a filing they dislike, and push the whole thing to a remote of
their own without tapedeck knowing or caring that they did.

Five paths are pinned here and everything else about the wiki's shape is not.
`wiki/CLAUDE.md` is the maintainer's brief: conventions, taxonomy, page templates, how
deep a note goes, what deserves its own page — all of it lives there and none of it lives
in this spec. `wiki/index.md` is the catalog, one markdown-linked line per wiki page,
rewritten on every accepted operation and covering every page in the wiki except the three
pinned files; it is the entry point for a human opening the directory and for anything
reading it later. `wiki/log.md` is the chronology and it is append-only — entries begin
`## [YYYY-MM-DD] <op> | <subject>`, and whatever the file said before an operation is still
the beginning of what it says after, byte for byte, so an operation can add to the record
and can never revise it. `wiki/notes/` holds free-form pages, and what goes in them, and
how they are organized, is the brief's business.

`wiki/sources/<video-id>.md` is one page per filed video, and its **existence is the
filed-state marker**. There is no manifest, no state file, no table of what has been
processed: the wiki says what it knows by containing a page about it, which is a claim a
user can inspect, delete, or write by hand. Each such page cites its own video with at
least one deep link in the layout contract's format, so the page is anchored to the
recording it describes.

First use scaffolds all of it, so no user ever has to assemble a wiki by hand before the
first filing: `wiki/` with `sources/` and `notes/` under it, the default `CLAUDE.md`, an
empty `index.md` and an empty `log.md`, `git init`, and one initial commit containing
exactly those files. Scaffolding happens when the wiki is absent and never again — a
`wiki/` that is already there is left as the user left it, and its brief in particular is
never re-written by a later run.

The brief is **scaffolded once, then user-owned** — exactly the arrangement `config.toml`
already has (SPEC-core-004): tapedeck writes a default so there is something to read and
edit on the first day, and from then on the file is the user's, never rewritten and never
migrated. The default brief describes the layout above, states the conventions tapedeck's
own gate will enforce, and offers starting taxonomy the user is expected to replace. A
brief the user has rewritten wholesale is the intended end state, not a fault condition.

The division is deliberate. This layer pins only what can be checked mechanically —
a page exists, a link resolves, the catalog is complete, the log grew at the end. Style,
structure, and subject matter are the user's, and a clause that dictated the shape of a
note would be specifying how someone else is allowed to think. Consumption follows from
the same restraint: the wiki is plain markdown files and `[[wikilinks]]`, readable by any
editor, `grep`, or agent that can open a directory. No graph database, no server, no
protocol — the durable artifact is the files.

Because the wiki is written by a maintainer reading a brief, and because the user edits it
by hand between filings, it is **accumulated, path-dependent state: versioned rather than
regenerable**. This is the one layer of tapedeck that SPEC-core-002 does not govern, and
the exception is chosen rather than tolerated. Filing the same videos in a different order,
or against a brief that has since been rewritten, produces a different and equally valid
wiki; nothing in the library can reconstruct the one that exists. That is why it gets git
and the derived layers do not: a transcript can be re-derived and thrown away, a wiki can
only be kept.
