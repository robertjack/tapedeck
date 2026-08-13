"""Both halves of system/contracts/ask-citations.md, because they are one promise.

Fast mode numbers what retrieval found: `prompt` hands the answerer those markers
and tells it they are the only ones that exist (SPEC-ask-002 — the wording is part
of this component's testable surface, not decoration), `sources_block` renders the
same numbers back from the same chunks, so `[2]` in the prose and `[2]` under
Sources are the same passage by construction, and `invented` is the gate between.

Librarian mode has no numbering to hold it — the agent reads the library itself and
writes its own deep links — so the check moves after the fact: `deep_links` collects
every link the answer offers, `unverified` asks the library whether each one is a
real moment in a real video.

Either way the model picks its citations and never decides whether they stand.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

MARKER = re.compile(r"\[(\d+)\]")
# A citation link, stopping before the punctuation that closes a markdown link or
# ends a sentence: the `)` of `](url).` is not part of the url.
LINK = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?|youtu\.be/)[^\s)\]<>\"']+")
# `t=` as YouTube writes it: bare seconds, `95s`, or `1h2m3s`.
OFFSET = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", re.IGNORECASE)

INSTRUCTIONS = """\
Answer the question below using only the numbered sources that follow it. They
are transcript excerpts from the asker's own video library, and they are all you
know here.

- Use only what the sources say. No outside knowledge, no inference past them,
  no source you were not given.
- Cite as you go: put a source's marker — [1], [2], and so on — immediately after
  each statement it supports. Use only the markers listed below.
- If the sources do not answer the question, reply exactly: not in the library
- Write the answer prose only. Do not write a Sources list of your own; tapedeck
  appends one built from this same numbering.\
"""


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, the shape citations are read in."""
    total = max(int(seconds), 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def deep_link(video_id: str, seconds) -> str:
    """A moment in a video, per system/contracts/library-layout.md."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


# --- fast mode: the numbering ---


def _citation(number: int, source) -> str:
    """`[n] <title> — <channel> @ <h:mm:ss>` — the contract's one citation line."""
    who = f"{source.title} — {source.channel}" if source.channel else source.title
    return f"[{number}] {who} @ {source.timestamp}"


def prompt(question: str, sources) -> str:
    """The whole of what the answerer is told: the rules, the sources, the question."""
    blocks = [INSTRUCTIONS, "Sources:"]
    for number, source in enumerate(sources, start=1):
        # The section name rides along inside the prompt, where it orients the model.
        head = _citation(number, source)
        head = f"{head} ({source.section})" if source.section else head
        blocks.append(f"{head}\n{source.text}".rstrip())
    blocks.append(f"Question: {question}")
    return "\n\n".join(blocks) + "\n"


def sources_block(sources) -> str:
    """The Sources section, assembled from what retrieval actually returned.

    Every retrieved chunk is listed, cited or not: the numbering the answerer was
    given is the numbering the reader sees, so `[2]` never has to be renumbered to
    stay true — and what ask read in order to answer is itself part of the answer.
    """
    lines = ["Sources:"]
    for number, source in enumerate(sources, start=1):
        lines += [_citation(number, source), f"    {source.url}"]
    return "\n".join(lines)


def invented(answer: str, count: int) -> list[int]:
    """Markers the answer cites that no retrieved source carries."""
    cited = {int(number) for number in MARKER.findall(answer)}
    return sorted(cited - set(range(1, count + 1)))


def document(answer: str, sources) -> str:
    """The two parts of the contract: prose as written, sources as retrieved."""
    return f"{answer.strip()}\n\n{sources_block(sources)}"


# --- librarian mode: the verification ---


def _offset(raw: str) -> int | None:
    """A `t=` value in seconds, or None when the link claims no moment."""
    match = OFFSET.fullmatch(raw.strip())
    if match is None or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def deep_links(answer: str) -> list[tuple[str, str, int | None]]:
    """Every citation the answer offers, as (url, video id, seconds into it)."""
    found = []
    for url in LINK.findall(answer):
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        video_id = (query.get("v") or [parts.path.strip("/")])[0]
        found.append((url, video_id, _offset(query.get("t", [""])[0])))
    return found


def unverified(links, videos) -> list[str]:
    """The citations the library cannot vouch for — one printable line each.

    A link is good when the library holds that video and the moment is inside it.
    An unknown duration cannot disprove a moment, so the link stands: this is a
    check against fabrication, not against gaps in metadata.
    """
    problems = []
    for url, video_id, seconds in links:
        duration = videos.get(video_id)
        if video_id not in videos:
            problems.append(f"{url} — no video {video_id!r} in the library")
        elif seconds is not None and duration is not None and seconds > duration:
            problems.append(
                f"{url} — {hms(seconds)} is past the end of {video_id} ({hms(duration)})"
            )
    return problems
