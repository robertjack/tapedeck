"""Both halves of system/contracts/ask-citations.md, because they are one promise.

Fast mode numbers what retrieval found: `prompt` gives the answerer those markers and
tells it they are the only ones there are (SPEC-ask-002 — that wording is testable
surface, not decoration), `sources_block` renders the same numbers back from the same
chunks, so `[2]` in the prose and `[2]` under Sources are one passage by construction,
and `invented` is the gate between.

Librarian mode has no numbering to hold it, so the check moves after the fact:
`deep_links` reads every link offered — a YouTube watch URL or a local `file://`
address (SPEC-ingest-005) — `unverified` asks the library whether each is a real
moment in a real video, and under `--video` `ask_for` states the scope going in while
`unverified` holds the answer to it coming back (SPEC-ask-003). Either way the model
picks its citations and never decides whether they stand.

`audit` is that check entire, and it is the only one there is: librarian mode runs it
on an answer and `python -m ask verify` runs it on whatever text a caller holds
(SPEC-ask-005). The verb publishes this function, it does not paraphrase it — two
readings of a citation would be two verdicts on the same link, each defensible in its
own evals, and the drift between them invisible until it matters (LESSON-0003).

A verifier is only as good as its reading, and a citation lives in a sentence: the
full stop that ends the sentence is prose, not URL and not part of the `t=` the URL
carries. Both halves of that matter and they pull in opposite directions — swallow
the punctuation into the id and a true citation is convicted; swallow it into the
offset, fail to parse, and call the link one that claims no moment, and a fabricated
9999s walks past the bounds check wearing a full stop. So the punctuation comes off
the link before anything is read out of it, and a `t=` that still cannot be read is a
citation that fails, never one that is waived.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

MARKER = re.compile(r"\[(\d+)\]")
# A citation link: a YouTube watch/short URL, or a local file:// address, ending
# where whitespace, a markdown `)`, or a bracket ends it.
LINK = re.compile(
    r"""(?:https?://(?:[\w-]+\.)*(?:youtube\.com|youtu\.be)/|file://)[^\s()\[\]<>"']+"""
)
# The characters that end a sentence rather than a URL.
PROSE = ".,;:!?\"'…»"
# `t=` as YouTube writes it: bare seconds, `95s`, or `1h2m3s`.
OFFSET = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", re.IGNORECASE)

UNCITED = (
    "no deep link anywhere in the text — nothing here can be traced to a moment "
    "in the library"
)

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


# --- librarian mode, and the `verify` verb that publishes its check ---


def ask_for(question: str, scope: str | None) -> str:
    """What goes to the librarian on stdin: the question, and any scope."""
    if not scope:
        return f"{question}\n"
    return f"{SCOPE_NOTE.format(video_id=scope)}\n\n{question}\n"


@dataclass(frozen=True)
class Citation:
    """One link an answer offers: where it points, and to what moment.

    A YouTube citation carries `video_id` and no `path`; a local citation carries
    `path` — the file it names — and no `video_id`, since a local video's id is a
    digest of its bytes and cannot be read out of the link itself (SPEC-ingest-005).
    `unverified` resolves whichever one is missing.

    `stated` is whether the link carried a `t=` at all, which is not the same
    question as whether `seconds` could be read out of it. A link with no `t=`
    claims no moment and there is nothing to bound; a link whose `t=` is unreadable
    claims a moment nobody can check, and that is a failed citation, not a free one.
    """

    url: str
    video_id: str | None
    path: str | None
    seconds: int | None
    stated: bool


def _moment(raw: str) -> int | None:
    """A `t=` value in seconds, or None when it cannot be read as one."""
    match = OFFSET.fullmatch(raw.strip().strip(PROSE))
    if match is None or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _parse_link(url: str) -> Citation:
    """One matched link, taken apart into what it points at and what it claims."""
    parts = urlsplit(url)
    stamps = parse_qs(parts.query, keep_blank_values=True).get("t") or []
    seconds = _moment(stamps[0]) if stamps else None
    stated = bool(stamps)
    if parts.scheme == "file":
        return Citation(url, None, unquote(parts.path), seconds, stated)
    video_id = (parse_qs(parts.query).get("v") or [parts.path.strip("/")])[0]
    return Citation(url, video_id, None, seconds, stated)


def deep_links(answer: str) -> list[Citation]:
    """Every citation the answer offers, read exactly as the contract reads them."""
    found = []
    for match in LINK.findall(answer):
        # The sentence's punctuation comes off before the URL is taken apart, so it
        # lands in neither the video id, the path, nor the offset.
        found.append(_parse_link(match.rstrip(PROSE)))
    return found


def unverified(links, library, scope: str | None = None) -> list[str]:
    """The citations the library cannot vouch for — one printable line each.

    A link is good when the library holds that video — resolved by path for a local
    citation, by id for a YouTube one (SPEC-ask-001) — the moment is inside it, and
    — under `--video` — it is the video asked about. An unknown duration cannot
    disprove a moment: this checks fabrication, not gaps in metadata.
    """
    problems = []
    for cite in links:
        if cite.path is not None:
            video_id = library.resolve_local(cite.path)
            if video_id is None:
                problems.append(f"{cite.url} — no library video at {cite.path!r}")
                continue
        else:
            video_id = cite.video_id
            if not library.holds(video_id):
                problems.append(f"{cite.url} — no video {video_id!r} in the library")
                continue
        if scope and video_id != scope:
            problems.append(f"{cite.url} — {video_id} is outside the --video {scope} scope")
            continue
        if cite.stated and cite.seconds is None:
            problems.append(f"{cite.url} — the moment this cites cannot be read")
            continue
        length = library.duration(video_id)
        if cite.seconds is not None and length is not None and cite.seconds > length:
            problems.append(
                f"{cite.url} — {hms(cite.seconds)} is past the end of "
                f"{video_id} ({hms(length)})"
            )
    return problems


def audit(text: str, library, scope: str | None = None, require_citation: bool = False):
    """Every way `text`'s citations fail the library, one printable line each.

    The whole of SPEC-ask-001's mechanical check in one call, so that the two callers
    that need it — librarian mode, and the `verify` verb it is published as — cannot
    reach different verdicts about the same link (SPEC-ask-005).

    `require_citation` is the one thing that honestly differs between them: an answer
    with no deep link has dodged the question, so librarian mode always demands one,
    while a page with none has simply made no claim to check and passes unless a
    caller asks otherwise.
    """
    links = deep_links(text)
    if not links:
        return [UNCITED] if require_citation else []
    return unverified(links, library, scope)
