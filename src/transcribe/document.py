"""The transcriber's output → library/<id>/transcript.json (contracts/transcript.schema.json).

A whisper CLI emits its own JSON: a leading space on every segment, a dozen
per-segment fields nobody downstream reads (`seek`, `tokens`, `avg_logprob`), and
after a retried window, segments out of time order. transcript.json is what the
archive renders and what ask cites timestamps from, so the narrowing happens
exactly here — the schema's properties and nothing else, text stripped, segments
ordered. Downstream never sees whisper's vocabulary.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

TRANSCRIPT_NAME = "transcript.json"
PRECISION = 3  # milliseconds; float noise past that is not information about the video


class BadTranscript(ValueError):
    """The transcriber's output holds no transcript worth storing."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _seconds(value):
    """A timestamp as the schema wants it: a non-negative number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(max(0.0, float(value)), PRECISION)


def _line(value) -> str:
    """Segment text with its whitespace tidied — whisper indents every line."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def segments(raw) -> list[dict]:
    """Whisper's segments as the schema has them: start, end, text, in time order."""
    kept = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        start, end = _seconds(item.get("start")), _seconds(item.get("end"))
        text = _line(item.get("text"))
        # A segment with no time cannot be deep-linked and a blank one has nothing
        # to quote: either way there is no moment here for the archive or ask to
        # point at. `end` is pulled forward rather than dropped, because a decoder
        # that reported them backwards still heard the words at `start`.
        if start is None or end is None or not text:
            continue
        kept.append({"start": start, "end": max(start, end), "text": text})
    kept.sort(key=lambda segment: (segment["start"], segment["end"]))
    return kept


def normalize(video_id: str, model: str, payload: dict, transcribed_at: str | None = None) -> dict:
    """The transcriber's payload as transcript.json, or BadTranscript if it holds none."""
    kept = segments(payload.get("segments"))
    if not kept:
        # The schema asks for at least one segment, and rightly: a transcript with
        # none is not a shorter transcript, it is a transcriber that did not work.
        # Storing it would leave an entry that every later run skips as done.
        raise BadTranscript("the transcriber returned no usable segments")
    document = {
        # The id is ours, not the transcriber's: it names the directory this is
        # written into, and the two disagreeing would break every deep link.
        "video_id": video_id,
        # Why a later, better transcript may replace this one (SPEC-core-002).
        "model": model,
    }
    language = payload.get("language")
    if isinstance(language, str) and language.strip():
        document["language"] = language.strip()
    document["transcribed_at"] = transcribed_at or _now()
    document["segments"] = kept
    return document


def write(entry: Path, document: dict) -> Path:
    """Atomic swap: a `--force` re-transcription keeps the old transcript readable
    until the new one is whole, and an interrupted write never leaves half a
    transcript for the archive to render as if it were the whole video."""
    target = entry / TRANSCRIPT_NAME
    # Dotted temp name: a crashed write stays invisible to anything listing an entry.
    tmp = entry / f".{TRANSCRIPT_NAME}.{os.getpid()}.tmp"
    try:
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return target
