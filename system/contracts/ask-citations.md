# Contract: ask answer formats

## Librarian mode (default)

The librarian answers in prose with **inline markdown deep links** as citations:
`[label](https://www.youtube.com/watch?v=<id>&t=<seconds>s)`.

Mechanically enforced by tapedeck after the answer returns (SPEC-ask-001):

- At least one deep link must be present.
- Every deep link must reference a video that exists in the library.
- Every timestamp must be within that video's duration.
- Any violation fails the command (exit 1) — the librarian may retrieve freely but
  may not fabricate a citation.

## Fast mode (`--fast`)

Output has exactly two parts:

```
<answer prose, with inline citation markers like [1], [2]>

Sources:
[1] <video title> — <channel> @ <h:mm:ss>
    https://www.youtube.com/watch?v=<id>&t=<seconds>s
```

- Every `[n]` marker in the answer must match a Sources entry.
- Sources entries reference only chunks actually retrieved for this question.
- The Sources section is assembled by tapedeck from retrieval results, never by
  the LLM; the LLM only chooses which markers to cite inline.
- If retrieval returns nothing, `ask --fast` exits 1 with "no sources in the
  library for this question" and the answerer is never invoked.
