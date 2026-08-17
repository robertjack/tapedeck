---
id: SPEC-wiki-011
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-wiki-004, SPEC-wiki-006]
---
A page may write *about* wiki links without writing one, and a rejected run still says what
it was doing.

**Code is not a link.** The gate resolves every `[[target]]` in every page against the page
names, over raw text, with no notion of markdown code. So a page that quotes the syntax —
in backticks, or in a fenced block — has its example read as a claim and the whole
operation rejected. This is not a rule anyone chose. `CLAUDE.md` dodges it by describing
the form in words ("wrapped in doubled square brackets") and `layout.py` carries a comment
explaining why, so the trap was known; what was missing is that the trap applies to every
page the maintainer writes, and nothing tells it so.

On 2026-08-17 an apply-mode `tend` edited seven notes and a source page, wrote a
chronology entry describing the linking discipline it had just worked on, and was rejected
whole for the `[[wikilink]]` inside that sentence. Twenty minutes of reasoning and a real
bill were discarded because a wiki about harnesses is not allowed to mention its own
syntax. A library whose subject is agents will keep trying to write that sentence.

So **wiki links inside inline code spans and fenced code blocks are not links**, for the
gate and for `lint` alike (SPEC-wiki-004's two must never disagree). This is ordinary
markdown semantics rather than an exemption invented here: a reader already understands
that backticks mean "the literal characters", and Obsidian renders it that way too, so the
contract's compatibility test is unaffected. Everything outside code is unchanged — a bare
`[[target]]` that resolves to nothing is still the defect it always was, and remains the
one thing nothing reading the wiki afterwards can route around.

**A rejected run still owes the user its account.** `perform` discards the tree and reports
the gate's complaints, and it drops the maintainer's product on the floor — so a rejection
loses not only the work but the agent's own description of what it had been attempting. The
run above spent twenty minutes reasoning about seven notes and left nothing to act on but
a list of file paths in the progress feed. That is the difference between a wasted run and
one a person can learn from, and it costs nothing to keep: a rejected operation prints the
product alongside the reasons, and the reasons still decide the exit code.

What does not change: the rollback. The product is words, not work — printing it admits
nothing to the wiki, and every byte the agent wrote is still discarded exactly as before.
