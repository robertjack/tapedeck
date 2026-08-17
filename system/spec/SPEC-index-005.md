---
id: SPEC-index-005
type: requirement
component: index
status: active
depends: [SPEC-index-001, SPEC-index-002, SPEC-index-003]
---
A paragraph's leading anchor is metadata, not prose. SPEC-archive-002 puts a deep link
at the start of every paragraph on the pages this index is derived from; the chunk
text this component indexes and excerpts **excludes those anchors** — the display
timestamp, the brackets, the URL, all of it — keeping only the prose that follows.
The section heading's own anchor was never chunk text and still is not.

Without this, the change upstream quietly poisons the search surface twice. First the
index: every chunk would carry `youtube`, `watch`, the video's own id and a scatter of
timestamp digits as indexable tokens, so `tapedeck search youtube` would match the
whole library and rank it by nothing — matches earned by plumbing, not by anything
anyone said. Second the excerpts: a result's text would open with
`[0:25:14](https://…&t=1514s)` before the words the query actually hit, which is
markdown link syntax shown raw in a surface whose entire job is the readable moment.
An anchor is for *following*, and search results already carry their own deep link
per SPEC-index-002; repeating a mangled copy inside the excerpt informs nobody.

The stripping is exact, not heuristic. What is removed is the leading construct
SPEC-archive-002 pins — one `[h:mm:ss](deep-link)` at the head of a paragraph, in the
layout contract's deep-link format — and nothing else: prose that mentions a URL or a
bracket stays prose, and a page written before SPEC-archive-002, with no paragraph
anchors at all, chunks exactly as it always has, which is what keeps `reindex` the
only migration anyone needs (SPEC-index-001). Everything else is untouched:
chunks are still one section each with the section's start and title, `update`
still produces the same rows a full `reindex` would, and search's own output —
ranking, `h:mm:ss`, the result's deep link, `--json` — is exactly SPEC-index-002.
