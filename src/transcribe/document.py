"""The transcriber's JSON → transcript.json (system/contracts/transcript.schema.json).

What a transcriber emits is its own business — padded text, per-segment decoding
stats, occasionally segments out of order. transcript.json is the shape every
downstream component reads, so normalization happens exactly here: only the
schema's own properties survive, text is one clean line, and segments come out
ordered so the archive renderer can trust their sequence.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

TRANSCRIPT_NAME = "transcript.json"


class BadTranscript(ValueError):
    """The transcriber's output cannot be normalized into transcript.json."""


def _number(value):
    """The value as a float, or None for anything that is not a plain number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def segments(raw) -> list[dict]:
    ordered = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        start, end = _number(item.get("start")), _number(item.get("end"))
        text = " ".join(str(item.get("text") or "").split())
        # A segment we cannot place in time, or one with no words, is not something
        # search or a citation could ever point at — drop it rather than store it.
        if start is None or end is None or not text:
            continue
        start = max(0.0, start)
        ordered.append({"start": start, "end": max(start, end), "text": text})
    ordered.sort(key=lambda segment: (segment["start"], segment["end"]))
    return ordered


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize(video_id: str, model: str, output, transcribed_at: str | None = None) -> dict:
    """Output as transcript.json: required keys first, optional ones only when real."""
    if not isinstance(output, dict):
        raise BadTranscript("the transcriber's output is not a JSON object")
    timed = segments(output.get("segments"))
    if not timed:
        raise BadTranscript("the transcriber returned no timestamped segments")
    document = {"video_id": video_id, "model": model}
    language = output.get("language")
    if isinstance(language, str) and language.strip():
        document["language"] = language.strip()
    document["transcribed_at"] = transcribed_at or _now()
    document["segments"] = timed
    return document


def write(entry: Path, document: dict) -> Path:
    """Atomic swap: a failed or interrupted run leaves no partial transcript behind,
    and a `--force` re-derive keeps the old transcript until the new one is whole."""
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
