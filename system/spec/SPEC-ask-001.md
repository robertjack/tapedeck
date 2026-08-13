---
id: SPEC-ask-001
type: requirement
component: ask
status: active
depends: [SPEC-index-002, SPEC-core-004]
---
`ask <question>` defaults to librarian mode. It requires a non-empty library and the
librarian brief (`CLAUDE.md` in the library home; missing brief exits 2), then invokes
the configured `[ask].librarian_command` as a shell command with cwd set to the library
home and the question on stdin. The librarian answers from the library files with
inline deep-link citations, and tapedeck verifies the answer mechanically before
accepting it: the answer must contain at least one YouTube deep link, and every deep
link must reference a video present in the library with a timestamp within that
video's duration — an absent or fabricated citation fails the command with exit 1.
An empty library exits 1 with "no sources in the library" without invoking the
librarian. `ask --fast <question>` preserves the strict retrieval pipeline: top-k
chunks via the index (default 8, `-k`), a prompt with numbered excerpts to
`[ask].answerer_command` on stdin, the Sources section assembled by tapedeck per the
citation contract, and empty retrieval refusing without invocation.
