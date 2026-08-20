"""The pure part of the archive component: inputs -> the exact bytes of a page.

Nothing in this module reads the clock, the environment, or the filesystem, so
byte-identical re-renders (SPEC-archive-001) fall out of the design instead of
being asserted after the fact. `page(meta, transcript) -> str` is the whole API.
"""

from __future__ import annotations

import math
from bisect import bisect_right

BLOCK_S = 300  # section length when meta.json declares no chapters
PARAGRAPH_GAP_S = 2.0  # silence long enough to start a new paragraph
PARAGRAPH_CHARS = 600  # soft cap, so an unbroken monologue still gets paragraphs

FRONTMATTER_KEYS = ("id", "title", "channel", "upload_date", "duration_s", "url")


def deep_link(url: str, seconds) -> str:
    """A moment in a video: the video's own url with t=<seconds>s appended as a
    query parameter (system/contracts/library-layout.md). One rule for both a
    YouTube watch url (already carries `?v=`, so t= joins with `&`) and a local
    `file://` url (no query yet, so t= opens one with `?`) — this module never
    asks where the video came from.
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(seconds)}s"


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, matching the search/ask contracts."""
    total = max(int(seconds), 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


# --- YAML frontmatter -------------------------------------------------------

_UNSAFE_FIRST = "-?:,[]{}#&*!|>'\"%@`"
_RESERVED_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "none", "~"}


def _reads_back_as_string(text: str) -> bool:
    """True when a plain YAML scalar would round-trip to this exact string."""
    if not text or text.strip() != text:
        return False
    if text[0] in _UNSAFE_FIRST:
        return False
    if ": " in text or text.endswith(":") or " #" in text:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return False
    if text.lower() in _RESERVED_WORDS:
        return False
    try:
        float(text)  # 2026, 1e3, .5 would come back as numbers
    except ValueError:
        return True
    return False


def yaml_scalar(value) -> str:
    """Render a frontmatter value, quoting only when a plain scalar would lie."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if _reads_back_as_string(text):
        return text
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


# --- sections ---------------------------------------------------------------


def _one_line(value) -> str:
    return " ".join(str(value).split())


def _seg_start(segment) -> float:
    return float(segment["start"])


def _seg_end(segment) -> float:
    return float(segment["end"])


def sections(meta, segments):
    """Ordered (start_seconds, title) pairs covering the whole transcript.

    `segments` must already be sorted by start; `page` guarantees that.
    """
    chapters = meta.get("chapters") or []
    if chapters:
        marks, seen = [], set()
        for chapter in sorted(chapters, key=lambda c: float(c["start_s"])):
            start = max(int(float(chapter["start_s"])), 0)
            if start in seen:  # two chapters on the same second: first one wins
                continue
            seen.add(start)
            marks.append((start, _one_line(chapter.get("title", ""))))
        # A video whose first chapter starts late still has words before it;
        # give them their own untitled section rather than a false chapter.
        if marks and marks[0][0] > 0 and segments and _seg_start(segments[0]) < marks[0][0]:
            marks.insert(0, (0, ""))
        if marks:
            return marks

    # Blocks cover the video, and never stop short of the last spoken word —
    # a transcript that overruns duration_s still gets a section to live in.
    span = float(meta.get("duration_s") or 0)
    needed = 0
    if segments:
        span = max(span, max(_seg_end(s) for s in segments))
        needed = int(max(_seg_start(s) for s in segments)) // BLOCK_S + 1
    count = max(1, needed, math.ceil(span / BLOCK_S))
    return [(i * BLOCK_S, "") for i in range(count)]


def _group(marks, segments):
    """Drop each segment into the section it starts in."""
    groups = [[] for _ in marks]
    starts = [start for start, _ in marks]
    for segment in segments:
        i = bisect_right(starts, _seg_start(segment)) - 1
        groups[max(i, 0)].append(segment)
    return groups


def _paragraphs(segments):
    """Merge segments into prose, breaking on silence or on length.

    Returns (start_seconds, text) pairs: the start is the paragraph's own
    first segment (SPEC-archive-002), never the section's and never
    interpolated, so two paragraphs in one section carry two addresses.
    """
    out, buf, size, prev_end, start = [], [], 0, 0.0, None
    for segment in segments:
        text = _one_line(segment.get("text", ""))
        if not text:
            continue
        if buf and (_seg_start(segment) - prev_end > PARAGRAPH_GAP_S or size >= PARAGRAPH_CHARS):
            out.append((start, " ".join(buf)))
            buf, size, start = [], 0, None
        if start is None:
            start = _seg_start(segment)
        buf.append(text)
        size += len(text) + 1
        prev_end = _seg_end(segment)
    if buf:
        out.append((start, " ".join(buf)))
    return out


# --- the page ---------------------------------------------------------------


def page(meta, transcript) -> str:
    """Render archive/<id>.md from validated meta + transcript structures."""
    url = str(meta["url"])
    segments = sorted(transcript["segments"], key=lambda s: (_seg_start(s), _seg_end(s)))
    marks = sections(meta, segments)

    lines = ["---"]
    lines += [f"{key}: {yaml_scalar(meta[key])}" for key in FRONTMATTER_KEYS]
    lines += ["---", ""]

    title = _one_line(meta["title"])
    if title:
        lines += [f"# {title}", ""]

    byline = " · ".join(
        part
        for part in (
            _one_line(meta.get("channel", "")),
            _one_line(meta.get("upload_date", "")),
            hms(meta.get("duration_s", 0)),
            _one_line(meta.get("url", "")),
        )
        if part
    )
    if byline:
        lines += [byline, ""]

    for (start, title), group in zip(marks, _group(marks, segments)):
        # Link first: the index recovers id, start seconds and title from the
        # heading alone, so archive pages remain its only input (SPEC-index-001).
        heading = f"## [{hms(start)}]({deep_link(url, start)})"
        lines.append(f"{heading} {title}" if title else heading)
        lines.append("")
        for p_start, paragraph in _paragraphs(group):
            anchor = f"[{hms(p_start)}]({deep_link(url, p_start)})"
            lines += [f"{anchor} {paragraph}", ""]

    return "\n".join(lines).rstrip("\n") + "\n"
