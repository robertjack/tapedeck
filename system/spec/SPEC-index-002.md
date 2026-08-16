---
id: SPEC-index-002
type: requirement
component: index
status: active
depends: [SPEC-index-001]
---
`search <query>` returns ranked matches, each carrying: video id, title, section start
timestamp rendered `h:mm:ss`, a text excerpt, and the deep link
`https://www.youtube.com/watch?v=<id>&t=<seconds>s`. `-k N` bounds the result count
(default 8). `--json` emits the same fields structurally. A query with no matches
prints nothing, exits 0, and `--json` yields `[]` — no results is an answer, not an
error.

A query is the whole of what follows the verb. Several words are one query, joined by
spaces: `search neural networks` asks about neural networks and is never a usage error.
People type phrases, and a search verb that accepts only single tokens has lost the
verb's point while still passing every eval written with one-word fixtures.

An absent index is not an empty one. When no database exists, `search` says so, names the
remedy, and exits non-zero; the quiet empty answer above belongs only to a query that
genuinely matched nothing in an index that exists. At the terminal, silence meaning "I
could not look" is indistinguishable from silence meaning "I looked and found nothing",
and the first is a broken library the user needs to hear about.

*(Both paragraphs promoted by the 2026-08-16 yield audit: an independent implementation
of this same clause rejected multi-word queries and answered a missing index with exit 0
and no output. Neither behavior was demanded by any of 233 evals; both had lived only in
the implementation.)*
