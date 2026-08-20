"""The index's only input: the bytes of one archive page.

`tapedeck.db` is derived from `archive/*.md` alone (SPEC-index-001), so this
module is the whole seam between the archive's render and our rows — page text in,
`Page` with its `Section`s out. Nothing here reads the filesystem, the clock or the
environment, which is what makes a chunk a pure function of the page it came from
and an incremental update indistinguishable from a full rebuild.

The page shape is the one SPEC-archive-001 pins: YAML frontmatter, then one
`## [h:mm:ss](deep-link) Title` heading per section, the title optional. A
section's `url` is the heading's own deep-link text, carried through verbatim —
never rebuilt from the video id — so a result addresses the moment the way the
page did, YouTube or a local file alike (SPEC-index-002, SPEC-ingest-005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
HEADING = re.compile(r"^##[ \t]+\[(?P<stamp>[^\]]*)\]\((?P<link>[^)]*)\)[ \t]*(?P<title>.*)$")
LINK_SECONDS = re.compile(r"[?&]t=(\d+)s?(?:&|$)")
STAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})$")
# The exact leading construct SPEC-archive-002 writes at the head of a paragraph —
# `[h:mm:ss](deep-link) ` addressing the moment with `...[?&]t=<seconds>s` — and
# nothing looser (SPEC-index-005). Scheme-agnostic on purpose: the layout contract
# is one deep-link rule for a YouTube watch url and a local `file://` one alike, so
# stripping the anchor never grew a second rule of its own either.
PARA_ANCHOR = re.compile(r"^\[[^\]]*\]\([^\s)]*[?&]t=\d+s\)[ \t]*")

FENCE = "---"
# The escapes the renderer emits inside a double-quoted frontmatter scalar.
UNESCAPE = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}


class PageError(ValueError):
    """An archive page that cannot be indexed as written."""


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, per SPEC-index-002."""
    total = max(int(seconds), 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class Section:
    """One chunk: where it starts, what it is called, where it points, what is
    said in it."""

    start_s: int
    title: str
    url: str
    text: str


@dataclass(frozen=True)
class Page:
    """One archive page: the video it describes, and its sections in order."""

    video_id: str
    title: str
    channel: str
    upload_date: str
    url: str
    duration_s: int | None
    sections: tuple[Section, ...]


def scalar(raw: str) -> str:
    """Read a frontmatter value back the way the renderer wrote it."""
    text = raw.strip()
    if len(text) < 2 or not (text.startswith('"') and text.endswith('"')):
        return text
    out, body, i = [], text[1:-1], 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(UNESCAPE.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def _frontmatter(lines: list[str]) -> tuple[dict, int]:
    """The leading `---` block's values, plus the line the body starts on."""
    if not lines or lines[0].strip() != FENCE:
        return {}, 0
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FENCE:
            return meta, i + 1
        key, sep, raw = line.partition(":")
        if sep and key.strip():
            meta[key.strip()] = scalar(raw)
    raise PageError("frontmatter is never closed")


def _seconds(heading: re.Match) -> int | None:
    """Where a section starts: the deep link decides, the stamp is the fallback."""
    link = LINK_SECONDS.search(heading["link"])
    if link:
        return int(link[1])
    stamp = STAMP.match(heading["stamp"].strip())
    if not stamp:
        return None
    hours, minutes, secs = stamp.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)


def _strip_anchor(paragraph: str) -> str:
    """Drop one paragraph's own leading deep-link anchor (SPEC-index-005)."""
    lines = paragraph.split("\n")
    lines[0] = PARA_ANCHOR.sub("", lines[0], count=1)
    return "\n".join(lines)


def _prose(lines: list[str]) -> str:
    """A section's body: paragraphs kept, blank runs and trailing space dropped,
    each paragraph stripped of its own leading anchor (SPEC-index-005)."""
    out: list[str] = []
    for line in lines:
        line = line.rstrip()
        if line or (out and out[-1]):
            out.append(line)
    while out and not out[-1]:
        out.pop()
    text = "\n".join(out)
    if not text:
        return text
    paragraphs = re.split(r"\n{2,}", text)
    return "\n\n".join(_strip_anchor(p) for p in paragraphs)


def _duration(raw) -> int | None:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def parse(text: str, stem: str | None = None) -> Page:
    """Parse one archive page. `stem` is the filename's id, when there is a file."""
    lines = text.splitlines()
    meta, body = _frontmatter(lines)

    video_id = meta.get("id") or stem or ""
    if not VIDEO_ID.fullmatch(video_id):
        raise PageError(f"no usable video id (frontmatter id: {meta.get('id')!r})")
    if stem and video_id != stem:
        # Every link on the page is built from the frontmatter id, so a mismatch
        # would index one video under another's name. Refuse rather than guess.
        raise PageError(f"frontmatter id {video_id!r} does not match the filename")

    sections: list[Section] = []
    open_section: tuple[int, str, str] | None = None
    buf: list[str] = []
    for line in lines[body:]:
        heading = HEADING.match(line)
        if heading is None:
            buf.append(line)
            continue
        if open_section is not None:
            sections.append(Section(*open_section, _prose(buf)))
        # Prose before the first heading is the page's byline, not a chunk; a
        # heading whose start second is unreadable takes its text down with it.
        start_s = _seconds(heading)
        buf = []
        open_section = (
            None if start_s is None else (start_s, heading["title"].strip(), heading["link"].strip())
        )
    if open_section is not None:
        sections.append(Section(*open_section, _prose(buf)))

    return Page(
        video_id=video_id,
        title=meta.get("title", ""),
        channel=meta.get("channel", ""),
        upload_date=meta.get("upload_date", ""),
        url=meta.get("url", ""),
        duration_s=_duration(meta.get("duration_s")),
        sections=tuple(sections),
    )
