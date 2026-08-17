---
id: SPEC-wiki-009
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-wiki-006, SPEC-wiki-008]
---
Every maintainer run that writes is handed a **map of what the wiki already holds** —
one line per page, its path and its own opening heading — and, for a filing, a short
ranked list of the pages whose vocabulary the new video actually shares. The map is built
fresh for each run, it travels in the task, and it is never a file in the wiki.

This is the other half of SPEC-wiki-008's problem, and the larger half. That clause
stopped tapedeck asking the agent to do bookkeeping; this one stops it asking the agent
to *discover* the wiki by reading it. The filing task says that connecting a video to
what is already here is the point of the exercise, and it is — but the maintainer is
given `Read`, `Grep` and `Glob` and no way to know which pages are worth opening, so it
opens broadly and guesses. Measured across the user's ten filings, the number of existing
notes each run rewrote was 0, 0, 3, 2, 9, 12, 12, 13, 20, 15 — linear in the size of the
wiki, against notes averaging 20KB each.

**What that costs is not what it first appears.** The two filings measured under
SPEC-wiki-008 cost $9.16 and $8.33, and only about a fifth of each was the agent writing:
69,311 and 67,117 output tokens, which at the maintainer's rates is under $1.75. The rest
— roughly four fifths — was input, and input on an agent run is not paid once. Every turn
re-reads the whole accumulated context, so a page the agent opens early is paid for again
on every turn that follows it. **A filing's cost is its context multiplied by its turn
count**, which is why reading twenty notes to find four is not merely twenty-times
wasteful but compounds with the length of the run.

A catalog line costs about 100 bytes against a note's 20KB. The map is the same knowledge
at roughly 1/200th the size, and because that size is then multiplied by every turn, the
saving compounds the same way the waste did. It also converts the growth term from
linear-in-bytes to linear-in-count — a wiki ten times this one still describes itself in
a few thousand tokens.

The map lists every page that is not one of the three pinned files, because a source page
is as linkable as a note and a maintainer that cannot see them will not link to them.
Each line is bounded: a page whose opening heading is a paragraph contributes a truncated
line, never an unbounded one, or the map inherits exactly the problem it exists to solve.
A wiki holding no such pages yields no map at all — not an empty heading, which reads to
an agent as a wiki whose contents were withheld.

For a filing, the map is accompanied by a **shortlist**: a separate, named list beside
the map naming a few of its pages again — the ones whose text shares the most distinctive
vocabulary with the archive page being filed, ranked, and few. A shortlist as long as the
map is not a shortlist, and one that *replaces* the map is worse than none: the pages it
leaves out are exactly the ones a maintainer would otherwise have discovered, so both are
present and the map is complete. It is computed mechanically, here, from the words on the
pages. This is not index's business and must not become it: `index` owns
FTS5 retrieval over *transcripts* for `search` and `ask` (SPEC-index-001), and a
persistent index of wiki prose is neither what it holds nor what this needs. Nothing here
is persisted, nothing is stemmed, and no seam is involved — it is a ranking of the pages
in front of it, thrown away when the run ends.

**The shortlist is offered as a guess and must be labelled as one.** An agent told these
are the relevant pages will read those and stop; the wording has to leave it free to
ignore the ranking and open something else, because the ranking knows about shared words
and nothing about shared ideas. The map is the durable half of this clause; the shortlist
is a convenience over it.

`tend` gets the map too, in both modes, and no shortlist in either — a tend is about the
wiki entire and has no video to rank against. It is the same argument as a filing's: a
run that must be told what the wiki contains before it can say anything useful about it
should be told, not left to find out at ten thousand tokens a page.

What the map is **not** is a file. Adding one to `wiki/` would put it under the acceptance
gate, oblige the catalog to list it, oblige its own links to resolve, and show it to
anyone who opens the vault in Obsidian — and `system/contracts/wiki-layout.md` pins five
entries as the whole tree. It is assembled into the task and exists nowhere else, so a
run leaves behind exactly the pages it wrote and nothing that describes them.
