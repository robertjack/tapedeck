# Contract: ask answer format

`tapedeck ask` output has exactly two parts:

```
<answer prose, with inline citation markers like [1], [2]>

Sources:
[1] <video title> — <channel> @ <h:mm:ss>
    https://www.youtube.com/watch?v=<id>&t=<seconds>s
[2] ...
```

Rules (mechanically checkable — SPEC-ask-001):

- Every `[n]` marker appearing in the answer must have a matching entry in Sources.
- Every Sources entry must reference a chunk that was actually retrieved for this
  question — the answerer cannot invent sources.
- The Sources section is assembled by tapedeck from retrieval results, never by the
  LLM; the LLM only chooses which markers to cite inline.
- If retrieval returns nothing, `ask` exits 1 with "no sources in the library for
  this question" and the answerer is never invoked.
