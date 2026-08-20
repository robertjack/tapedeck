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
accepting it: the answer must contain at least one deep link, and every deep link must
reference a video present in the library with a timestamp within that video's
duration — an absent or fabricated citation fails the command with exit 1. A deep link
is the layout contract's form for either kind of video this library holds: a YouTube
watch URL, or the `file://` address of a local one (SPEC-ingest-005). A local
citation is resolved to its entry by the path it names and then checked exactly as a
YouTube citation is — same duration bound, same verdict — because the guarantee this
component sells is that a cited moment exists, and where the video came from does not
change what that promise is worth.
Verification is only as good as the reading it is done from, so citations are read
exactly per contracts/ask-citations.md: sentence punctuation trailing a link is prose
and belongs to neither the URL nor its `t=` value, and a video whose duration is
unknown — `duration_s: 0`, or metadata that cannot be read — bounds nothing, so the
upper-bound check is waived for it while the video-exists check still stands. A
citation must not be refused for the punctuation that ends its sentence, and must not
escape the bounds check by carrying some.
An empty library exits 1 with "no sources in the library" without invoking the
librarian. `ask --fast <question>` preserves the strict retrieval pipeline: top-k
chunks via the index (default 8, `-k`), a prompt with numbered excerpts to
`[ask].answerer_command` on stdin, the Sources section assembled by tapedeck per the
citation contract, and empty retrieval refusing without invocation.
