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
