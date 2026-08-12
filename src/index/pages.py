"""The one input this component has: archive/<id>.md.

The index is derived from archive pages alone (SPEC-index-001), so this module is
the whole surface between the archive's render and our chunks — it turns a page's
bytes into (video metadata, sections) and touches neither the library nor the
database. Nothing here reads the clock, the environment, or the filesystem.

The page shape is pinned by SPEC-archive-001: YAML frontmatter, then one
`## [h:mm:ss](deep-link) Title` heading per section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
HEADING = re.compile(r"^##[ \t]+\[(?P<stamp>[^\]]*)\]\((?P<link>[^)]*)\)[ \t]*(?P<title>.*)$")
LINK_SECONDS = re.compile(r"[?&]t=(\d+)s?(?:&|$)")
STAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})$")

FRONTMATTER_FENCE = "---"
# Escapes the renderer emits inside a double-quoted frontmatter scalar.
UNESCAPE = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}


class PageError(ValueError):
    """An archive page that cannot be indexed as written."""


def hms(seconds) -> str:
    """Seconds as h:mm:ss — hours unpadded, per SPEC-index-002."""
    total = max(int(seconds), 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def deep_link(video_id: str, seconds) -> str:
    """A moment in a video, per system/contracts/library-layout.md."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


@dataclass(frozen=True)
class Section:
    """One chunk: where it starts, what it is called, what is said in it."""

    start_s: int
    title: str
    text: str


@dataclass(frozen=True)
class Page:
    video_id: str
    title: str
    channel: str
    upload_date: str
    url: str
    duration_s: int | None
    sections: tuple[Section, ...]


def scalar(raw: str) -> str:
    """Read back a frontmatter value the way the renderer wrote it."""
    text = raw.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        out, body, i = [], text[1:-1], 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                out.append(UNESCAPE.get(body[i + 1], body[i + 1]))
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    return text


def _frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Parse the leading `---` block; return its values and the body's first line."""
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}, 0
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_FENCE:
            return meta, i + 1
        key, sep, raw = line.partition(":")
        if sep and key.strip():
            meta[key.strip()] = scalar(raw)
    raise PageError("frontmatter is never closed")


def _seconds(heading: re.Match) -> int | None:
    """Section start: the deep link is authoritative, the stamp is the fallback."""
    link = LINK_SECONDS.search(heading["link"])
    if link:
        return int(link[1])
    stamp = STAMP.match(heading["stamp"].strip())
    if stamp:
        hours, minutes, secs = stamp.groups()
        return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)
    return None


def _prose(lines: list[str]) -> str:
    """A section's body: paragraphs kept, blank runs and trailing space dropped."""
    out: list[str] = []
    for line in lines:
        line = line.rstrip()
        if line or (out and out[-1]):
            out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def _duration(raw) -> int | None:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def parse(text: str, stem: str | None = None) -> Page:
    """Parse one archive page. `stem` is the filename's id, when there is a file."""
    lines = text.splitlines()
    meta, start = _frontmatter(lines)

    video_id = meta.get("id") or stem or ""
    if not VIDEO_ID.fullmatch(video_id):
        raise PageError(f"no usable video id (frontmatter id: {meta.get('id')!r})")
    if stem and video_id != stem:
        # The page's own links are built from its frontmatter id, so a mismatch
        # would index one video under another's name. Refuse rather than guess.
        raise PageError(f"frontmatter id {video_id!r} does not match the filename")

    sections: list[Section] = []
    current: tuple[int, str] | None = None
    buf: list[str] = []
    for line in lines[start:]:
        heading = HEADING.match(line)
        if heading is None:
            buf.append(line)
            continue
        if current is not None:
            sections.append(Section(current[0], current[1], _prose(buf)))
        seconds = _seconds(heading)
        buf = []
        current = None if seconds is None else (seconds, heading["title"].strip())
    if current is not None:
        sections.append(Section(current[0], current[1], _prose(buf)))

    return Page(
        video_id=video_id,
        title=meta.get("title", ""),
        channel=meta.get("channel", ""),
        upload_date=meta.get("upload_date", ""),
        url=meta.get("url", ""),
        duration_s=_duration(meta.get("duration_s")),
        sections=tuple(sections),
    )
