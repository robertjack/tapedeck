"""Both halves of system/contracts/ask-citations.md, because they are one promise.

Fast mode numbers what retrieval found: `prompt` gives the answerer those markers and
tells it they are the only ones there are (SPEC-ask-002 — that wording is testable
surface, not decoration), `sources_block` renders the same numbers back from the same
chunks, so `[2]` in the prose and `[2]` under Sources are one passage by construction,
and `invented` is the gate between.

Librarian mode has no numbering to hold it, so the check moves after the fact:
`deep_links` collects every link offered, `unverified` asks the library whether each
is a real moment in a real video, and under `--video` `ask_for` states the scope
going in while `unverified` holds the answer to it coming back (SPEC-ask-003).
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
Answer the question below using only the numbered sources that follow it. They are
transcript excerpts from the asker's own video library, and all you know here.

- Use only what the sources say: no outside knowledge, no inference past them, no
  source you were not given.
- Cite as you go: put a source's marker — [1], [2], and so on — immediately after
  each statement it supports. Use only the markers listed below.
- If the sources do not answer the question, reply exactly: not in the library
- Write the answer prose only; tapedeck appends the Sources list.\
"""

# The librarian is otherwise handed the question and nothing else — its rules live in
# the library's CLAUDE.md. A scope is the exception: not a standing rule but this
# run's boundary, and it cannot honour one it was never told (SPEC-ask-003).
SCOPE_NOTE = """\
Scope: answer only from the library video {video_id} — library/{video_id}/ and its
archive page archive/{video_id}.md. Ignore every other video and cite only this one:
a link elsewhere is rejected even to a video the library has.\
"""


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, the shape citations are read in."""
    total = max(int(seconds), 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def deep_link(video_id: str, seconds) -> str:
    """A moment in a video, per contracts/library-layout.md."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


# --- fast mode ---


def _citation(number: int, source) -> str:
    """`[n] <title> — <channel> @ <h:mm:ss>`: the contract's citation line."""
    who = f"{source.title} — {source.channel}" if source.channel else source.title
    return f"[{number}] {who} @ {source.timestamp}"


def prompt(question: str, sources) -> str:
    """The whole of what the answerer is told: the rules, the sources, the question."""
    blocks = [INSTRUCTIONS, "Sources:"]
    for number, source in enumerate(sources, start=1):
        # The section name rides inside the prompt, where it orients the model.
        head = _citation(number, source)
        head = f"{head} ({source.section})" if source.section else head
        blocks.append(f"{head}\n{source.text}".rstrip())
    blocks.append(f"Question: {question}")
    return "\n\n".join(blocks) + "\n"


def sources_block(sources) -> str:
    """The Sources section, assembled from what retrieval actually returned.

    Every retrieved chunk is listed, cited or not: the numbering the answerer was
    given is the numbering the reader sees, so `[2]` is never renumbered to stay true.
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


# --- librarian mode ---


def ask_for(question: str, scope: str | None) -> str:
    """What goes to the librarian on stdin: the question, and any scope."""
    if not scope:
        return f"{question}\n"
    return f"{SCOPE_NOTE.format(video_id=scope)}\n\n{question}\n"


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


def unverified(links, videos, scope: str | None = None) -> list[str]:
    """The citations the library cannot vouch for — one printable line each.

    A link is good when the library holds that video, the moment is inside it, and —
    under `--video` — it is the video asked about. An unknown duration cannot
    disprove a moment: this checks fabrication, not gaps in metadata.
    """
    problems = []
    for url, video_id, seconds in links:
        duration = videos.get(video_id)
        if video_id not in videos:
            problems.append(f"{url} — no video {video_id!r} in the library")
        elif scope and video_id != scope:
            problems.append(f"{url} — {video_id} is outside the --video {scope} scope")
        elif seconds is not None and duration is not None and seconds > duration:
            problems.append(
                f"{url} — {hms(seconds)} is past the end of {video_id} ({hms(duration)})"
            )
    return problems
