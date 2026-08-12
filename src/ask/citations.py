"""The numbering: what the model is handed, and what it may hand back.

Both halves of system/contracts/ask-citations.md live here, because they are one
promise. `prompt` numbers the retrieved chunks and tells the answerer those
markers are the only ones that exist (SPEC-ask-002 — the wording is part of the
component's testable surface, not decoration). `sources_block` renders the same
numbers back from the same chunks, so `[2]` in the prose and `[2]` under Sources
are the same passage by construction. `invented` is the gate between them: an
answerer citing a marker it was never given has left the library, and tapedeck
would rather print nothing than a citation it cannot stand behind.

The model chooses which markers to use. It never writes one.
"""

from __future__ import annotations

import re

MARKER = re.compile(r"\[(\d+)\]")

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


def _citation(number: int, source) -> str:
    """`[n] <title> — <channel> @ <h:mm:ss>` — the contract's one citation line."""
    who = f"{source.title} — {source.channel}" if source.channel else source.title
    return f"[{number}] {who} @ {source.timestamp}"


def _excerpt_heading(number: int, source) -> str:
    """The same line inside the prompt, where the section name orients the model."""
    line = _citation(number, source)
    return f"{line} ({source.section})" if source.section else line


def prompt(question: str, sources) -> str:
    """The whole of what the answerer is told: the rules, the sources, the question."""
    blocks = [INSTRUCTIONS, "Sources:"]
    for number, source in enumerate(sources, start=1):
        blocks.append(f"{_excerpt_heading(number, source)}\n{source.text}".rstrip())
    blocks.append(f"Question: {question}")
    return "\n\n".join(blocks) + "\n"


def sources_block(sources) -> str:
    """The Sources section, assembled by tapedeck from what retrieval actually returned.

    Every retrieved chunk is listed, cited or not: the numbering the answerer was
    given is the numbering the reader sees, so `[2]` never has to be renumbered to
    stay true — and what ask read in order to answer is itself part of the answer.
    """
    lines = ["Sources:"]
    for number, source in enumerate(sources, start=1):
        lines.append(_citation(number, source))
        lines.append(f"    {source.url}")
    return "\n".join(lines)


def invented(answer: str, count: int) -> list[int]:
    """Markers the answer cites that no retrieved source carries."""
    cited = {int(number) for number in MARKER.findall(answer)}
    return sorted(cited - set(range(1, count + 1)))


def document(answer: str, sources) -> str:
    """The two parts of the contract: the prose as written, the sources as retrieved."""
    return f"{answer.strip()}\n\n{sources_block(sources)}"
