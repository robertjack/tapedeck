# Contract: the tapedeck wiki layout

The wiki is the library's prose side: what the videos *say*, written down by hand and by
agent, in files a person can read without tapedeck installed. It is deliberately thin —
plain markdown, `[[wikilinks]]`, and git. There is no graph database, no server and no
protocol; anything that cannot be recovered by reading the files is not part of this
contract.

Additive changes only, for the same reason as the library layout: a wiki written by an
older tapedeck must stay valid under a newer one.

## Location

`$TAPEDECK_HOME/wiki/`, and it is **its own git repository** — not a submodule of the
tapedeck code repo, not tracked by it, not tracked by anything else. The wiki's history
is the wiki's own; it records what was learned about the library, on its own clock,
independent of tapedeck's releases.

```
$TAPEDECK_HOME/
  wiki/                        # its own git repo — `git init` on first use
    CLAUDE.md                  # the maintainer's brief — scaffolded once, then user-owned
    index.md                   # catalog: one markdown-linked line per page
    log.md                     # append-only chronology of accepted operations
    sources/<video-id>.md      # one per filed video; its existence is the filed marker
    notes/                     # free-form pages; their organization belongs to the brief
```

Those five entries are the whole pinned tree. Everything else — how notes are named and
foldered, what a note is for, which taxonomy or tags apply, when a claim earns a page —
is governed by `CLAUDE.md` and is none of this contract's business. The specs pin only
what a machine can check.

A wiki that exists is always a git repository with at least one commit: the scaffold
itself is committed (SPEC-wiki-001), so every later operation has a clean point to
compare against and to fall back to.

## `index.md`

The catalog. Every page in the wiki except the three pinned files (`CLAUDE.md`,
`index.md`, `log.md`) is linked from it, by an ordinary markdown link whose target is
the page's path relative to the wiki root:

```
- [Sources](sources/dQw4w9WgXcQ.md) — Rick Astley, "Never Gonna Give You Up"
- [Cache invalidation](notes/cache-invalidation.md)
```

One line per page, and the link is the pinned part. Grouping, headings, ordering,
annotation, whether the trailing dash carries a summary at all — the brief decides.
The invariant is only that no page is orphaned from the catalog: opening `index.md` is
how a reader learns what is in here, and a page the catalog does not mention is a page
nobody will find.

Keeping that invariant is **tapedeck's job, not the maintainer's** (SPEC-wiki-008).
After an operation's agent exits and before the result is judged, tapedeck appends a
line for every page that has none, annotated with the page's own opening heading. It
**appends and never regenerates**: everything above that the brief decides is decided in
this file, and rewriting it would overrule the user on every run. A maintainer may still
write catalog lines of its own — one that does is left alone — but it is no longer asked
to, and a page it forgot is no longer a rejected operation.

## `log.md`

Append-only chronology. Every entry starts with a line of exactly this shape:

```
## [YYYY-MM-DD] <op> | <subject>
```

`<op>` is the operation that wrote the entry (`file`, in round one); `<subject>` is what
it acted on — a video id, a topic, whatever the brief prefers. Prose below the heading
is free-form.

**Every accepted operation appends exactly one entry, and tapedeck is what guarantees
that count** (SPEC-wiki-008). Where the maintainer wrote a well-formed entry of its own,
that entry stands. Where it wrote none — the ordinary case, since nothing asks it to —
tapedeck appends one before the result is judged: the date, the `<op>` and the subject are
tapedeck's own — the subject being what this file already documents, a video id for a
filing and a short label for an operation with no single subject, on one line and free of
markdown so `grep "^## \["` keeps working — and the maintainer's product is the prose
beneath it. An operation whose agent narrated nothing still gets an
entry, since the operation still happened. Where that maintainer streams its run, the
entry also records what it cost — the model that answered, the duration, the total input
tokens and how many of them came from cache, the output tokens, and the price — because
whether keeping this wiki is getting more expensive is a question only the chronology is
in a position to answer. Counts are plain integers with no thousands separators, so the
log stays summable with `awk` for the same reason the heading shape keeps it greppable. A
maintainer that does not stream simply contributes no such line.

Append-only is mechanical, not aspirational: after any operation the previous content of
`log.md` must still be a **byte-prefix** of the new content. Entries are never reworded,
reordered, deduplicated or tidied — a chronology that gets rewritten is a chronology
nobody can trust, and rewriting is exactly what an agent asked to "keep the log neat"
will do.

The heading shape is fixed so the log stays greppable without tooling:

```
grep "^## \[" log.md | tail -5
```

## `sources/<video-id>.md`

One page per filed video. The basename is the video id exactly as ingest defines it,
plus `.md` — the id grammar is ingest's vocabulary and is consumed, never re-derived
here (LESSON-0003).

**The file's existence is the filed-state marker.** There is no registry, no database
column, no field to keep in sync: `ls wiki/sources/` answers "what has been filed", and
`test -e wiki/sources/<id>.md` answers it for one video. State that lives in the
filesystem cannot disagree with itself.

Each source page must cite its own video with at least one deep link in the library
layout's format (`https://www.youtube.com/watch?v=<video-id>&t=<seconds>s`). A source
page that says nothing anchored in the video it is about is a summary of a memory, not
a reading of a recording, and it is the failure mode this rule exists to catch.

Deep links anywhere in the wiki are read and verified under
`system/contracts/ask-citations.md` — the trailing-punctuation rule and the
unknown-duration waiver included. Those reading rules are ask's vocabulary; the wiki
consumes ask's published verification boundary rather than growing a second copy of them
(LESSON-0003).

## Wikilinks

Pages link to each other as `[[target]]` or `[[target|alias]]`. Resolution is the
simplest rule that works, and it is the whole rule:

- the target is the text before the first `|`;
- it is matched **case-sensitively** against page basenames with `.md` stripped;
- any page anywhere under `wiki/` may satisfy it — no paths, no extensions, no fuzzy or
  nearest-match behaviour;
- **it is not a link at all inside an inline code span or a fenced code block**
  (SPEC-wiki-011). Backticks mean the literal characters, here as everywhere else in
  markdown, and Obsidian renders them that way too — so a page may quote the syntax while
  writing about the wiki, and only prose outside code makes a claim that has to resolve.

So `[[dQw4w9WgXcQ]]` resolves to `sources/dQw4w9WgXcQ.md` from any depth. Every wikilink
in every page must resolve; a dangling link is a page the writer believed existed, and
believing that is how a wiki quietly forks into two half-written halves.

## Obsidian compatibility

A stated goal, not an afterthought: `$TAPEDECK_HOME/wiki/` opens as an Obsidian vault
with no conversion, no import and no plugin. That is what keeps the format honest —
plain markdown files, `[[wikilinks]]`, no required frontmatter, no proprietary index,
nothing that only tapedeck can read. Any future addition to this contract must survive
the same test: if the vault stops being readable by a plain markdown editor, the
addition is wrong.

## Write authority

Among tapedeck's components, the wiki component is the **sole writer** of everything
under `wiki/` (SPEC-core-001). No other component writes the wiki, and the only reading
another component does is the one this contract publishes: the existence of
`sources/<video-id>.md`, which cli's `rm` asks about so it can say the wiki still holds
a page for a video it just removed (SPEC-cli-009). Asking that question changes nothing
and reads no prose; everything else in the tree is wiki's and the user's. wiki writes
nothing outside it either — in particular it does not write `config.toml`, which is
cli's.

Unlike the rest of the library, though, the user is a co-author here by design. Hand
edits are expected, in any editor, at any time. Before it operates, tapedeck commits
whatever is pending in the working tree as a **`user edits`** commit, so that the
pre-run commit already contains the user's work; an operation that has to roll back
therefore rolls back to a state that still has it. Nothing a person typed is ever lost
to a machine's failed attempt.

| path | sole writer |
|---|---|
| `wiki/CLAUDE.md` | user (scaffolded once by wiki with defaults, then never touched by it) |
| `wiki/index.md`, `wiki/log.md` | wiki mechanically (SPEC-wiki-008), plus the maintainer and the user by hand |
| `wiki/sources/*.md`, `wiki/notes/**` | wiki, plus the user by hand |

`CLAUDE.md` is the one file the maintainer is forbidden to change. It is where the user
states the conventions the maintainer must follow, and a maintainer that may edit its
own instructions has no instructions — it has a draft. Tapedeck enforces this
mechanically rather than by asking nicely: the acceptance gate compares the file against
the pre-run commit byte for byte and rejects the whole operation on any difference
(SPEC-wiki-002).
