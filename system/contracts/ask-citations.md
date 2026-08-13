# Contract: ask answer formats

## Librarian mode (default)

The librarian answers in prose with **inline markdown deep links** as citations:
`[label](https://www.youtube.com/watch?v=<id>&t=<seconds>s)`.

Mechanically enforced by tapedeck after the answer returns (SPEC-ask-001):

- At least one deep link must be present.
- Every deep link must reference a video that exists in the library.
- Every timestamp must be within that video's duration, where the duration is known.
- Any violation fails the command (exit 1) — the librarian may retrieve freely but
  may not fabricate a citation.

### Where a citation's URL ends

A citation sits in a sentence, and the sentence's punctuation is not part of it. The
URL ends at the `)` closing the markdown link and at any prose character that follows
or precedes nothing — `.` `,` `;` `:` `!` `?` `"` `'` and the like are trailing prose,
never URL, and never part of the `t=` value the URL carries.

Both mistakes are the same mistake and both are forbidden:

- `[see](https://www.youtube.com/watch?v=<id>&t=95s).` ending a sentence is a citation
  of second 95 of `<id>`. Verified as written, it must pass — swallowing the `.` into
  the id or the offset turns a true citation into a reported fabrication.
- `[see](https://www.youtube.com/watch?v=<id>&t=99999s).` past the end of `<id>` is a
  fabrication and must be caught. A `t=` value the parser gives up on must never be
  read as "this link claims no moment" and waved through the bounds check.

### Unknown durations

`duration_s: 0` in `meta.json` means the source withheld the duration, not that the
video is zero seconds long: ingest writes `0` when the fetcher's `info.json` carries
no duration. An unknown duration cannot disprove a moment, so the upper-bound check is
waived for such a video exactly as it is for one whose `meta.json` is missing or
unreadable. What still applies: the video must exist in the library, and under
`--video` it must be the video in scope. This check is for fabrication, not for gaps
in metadata — refusing a truthful answer because the library never learned how long a
video runs is the failure mode, and in default librarian mode it exits 1 on an answer
that was correct.

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
- Fast mode reads the index component's `tapedeck.db` directly, and accepts only a
  database of the shape this build searches under (SPEC-ask-004): matching schema
  version and matching tokenizer. Anything else is refused like a missing index —
  exit 1 carrying the reindex hint, answerer never invoked — because rows written
  under another tokenizer are not rows this build can match against, and a silent
  half-answer from them is worse than no answer.
