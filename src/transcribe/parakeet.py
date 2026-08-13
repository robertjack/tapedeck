"""parakeet-mlx JSON → the whisper shape the transcriber seam requires (SPEC-transcribe-002).

parakeet-mlx is a better transcriber than whisper on some material, and swapping
to it must stay what SPEC-core-004 promises: an edit to config.toml, not a change
to tapedeck. The only thing standing in the way is vocabulary — parakeet calls
them `sentences` and hangs per-token times and confidences off each one, where the
seam reads `segments` of start, end and text. That difference is a filter, so this
is one: parakeet on stdin, whisper on stdout, nothing else in the process.

Order and timestamps come through untouched. This is an adapter, not a
normalizer — `document.normalize` still does the ordering and tidying downstream,
and doing any of it twice would only put two opinions on the same bytes.
"""

from __future__ import annotations

import json

SENTENCES = "sentences"


class NotParakeet(ValueError):
    """stdin held something that is not parakeet-mlx JSON."""


def _number(value) -> bool:
    """A JSON number, and not the bool that Python counts as one."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _segment(sentence) -> dict | None:
    """One sentence as a segment: the three fields the seam reads, and no more.

    Everything else parakeet knows about a sentence — per-token times, per-token
    and per-sentence confidences, durations — is dropped here rather than passed
    along, because transcript.json's schema forbids extra properties and nothing
    downstream has ever asked what a token was.
    """
    if not isinstance(sentence, dict):
        return None
    start, end, text = sentence.get("start"), sentence.get("end"), sentence.get("text")
    if not _number(start) or not _number(end) or not isinstance(text, str) or not text.strip():
        return None
    return {"start": float(start), "end": float(end), "text": text.strip()}


def adapt(text: str) -> dict:
    """Parakeet's JSON as whisper's, or NotParakeet if that is not what this is.

    The shape is checked before a byte is written, because this filter runs inside
    a shell pipeline whose `> "$TAPEDECK_OUT"` has already created the file it
    writes to. Emitting half a document there and then failing would hand the
    seam something that parses; failing with an empty stdout leaves it something
    that plainly does not, and the run stops where it should.
    """
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise NotParakeet(f"stdin is not JSON — {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get(SENTENCES), list):
        raise NotParakeet(
            'stdin is not parakeet-mlx JSON — expected an object with a "sentences" array'
        )
    kept = [segment for segment in map(_segment, payload[SENTENCES]) if segment]
    if not kept:
        # Parakeet's own shape, but holding no moment anyone could deep-link to.
        # Passed on, it would become a transcript that fails the schema one step
        # later, with the transcriber blamed for what arrived here already empty.
        raise NotParakeet("parakeet JSON with no sentence carrying a start, an end and text")
    return {"segments": kept}
