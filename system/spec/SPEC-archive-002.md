---
id: SPEC-archive-002
type: requirement
component: archive
status: active
depends: [SPEC-archive-001]
---
Every paragraph is addressable, not just every section. The renderer already breaks a
section's transcript into paragraphs deterministically; each of those paragraphs now
**opens with its own deep link**: `[h:mm:ss](deep-link) ` — the timestamp of the
paragraph's first segment, in the layout contract's deep-link format and the same
`h:mm:ss` display the section headings use — followed by the paragraph's prose on the
same line. Section headings are unchanged, and so is everything SPEC-archive-001 says:
same frontmatter, same chapter-or-five-minute sectioning, byte-identical re-renders,
`render-all` always possible.

Why the section anchor is not enough: the section is the *coarsest* moment the page
can name, and it is the only one it names today. A chapterless video's sections are
five-minute blocks, so every quote inside one collapses to the block's start — the
user's own wiki cites three distinct claims from one video at the same `t=1500s`, and
its maintainer has twice complained in the log about citations naming the nearest
preceding heading rather than the sentence they belong to. The precision has been in
`transcript.json` all along, segment by segment; the page just discarded it at the
paragraph seam. A reader following any consumer of this page — the wiki brief says
*copy timestamps from the archive page, never reconstruct one* — inherits whatever
granularity the page carries, so the page carries the paragraph's.

The anchor is the paragraph's address, not part of its prose. It stands at the start
of the paragraph's line, exactly one per paragraph, and the paragraph's text follows
it unmodified — a consumer that wants the prose alone (the index does; SPEC-index-005)
can take everything after the leading anchor, and a consumer that wants the moment
(the wiki maintainer does) copies the anchor whole. Timestamps come from the
transcript's own segment starts, never interpolated or rounded to the section: two
paragraphs in one section carry two different anchors, and a paragraph whose first
segment starts one second after its section heading carries that one-second-later
address.
