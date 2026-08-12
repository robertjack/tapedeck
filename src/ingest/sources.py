"""YouTube addresses → the canonical 11-character video id (SPEC-ingest-001).

The id is the library's primary key, so every form of an address for the same
video has to land on the same `library/<id>/`. Anything we cannot read as a
single YouTube video is a usage error rather than a guess — a wrong id would
silently start a second entry for a video already in the library.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
SUBDOMAINS = ("www.", "m.", "music.")
# Paths that carry the id as their next segment: /shorts/<id>, /embed/<id>, …
ID_PATHS = ("shorts", "embed", "live", "v")


class Unrecognized(ValueError):
    """Not an address for a single YouTube video."""


def watch_url(video_id: str) -> str:
    """The canonical watch URL — the same form the layout contract deep-links to."""
    return f"https://www.youtube.com/watch?v={video_id}"


def _host(netloc: str) -> str:
    host = netloc.rsplit("@", 1)[-1].split(":")[0].lower()
    for prefix in SUBDOMAINS:
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def canonical_id(text: str) -> str:
    """The 11-character id inside `text`, or Unrecognized."""
    raw = text.strip()
    if VIDEO_ID.fullmatch(raw):
        return raw
    if not raw:
        raise Unrecognized("no video address given")
    # A bare host/path ("youtu.be/<id>") is an address too; urlparse needs a scheme.
    try:
        url = urlparse(raw if "//" in raw else f"https://{raw}")
    except ValueError as exc:
        raise Unrecognized(f"{text!r} is not a usable address — {exc}") from exc
    host = _host(url.netloc)
    if host not in HOSTS:
        raise Unrecognized(f"{text!r} is not a YouTube video address")
    segments = [segment for segment in url.path.split("/") if segment]
    candidate = None
    if host == "youtu.be":
        candidate = segments[0] if segments else None
    elif segments[:1] == ["watch"]:
        candidate = parse_qs(url.query).get("v", [None])[0]
    elif len(segments) > 1 and segments[0] in ID_PATHS:
        candidate = segments[1]
    if candidate and VIDEO_ID.fullmatch(candidate):
        return candidate
    raise Unrecognized(f"{text!r} has no video id in it")
