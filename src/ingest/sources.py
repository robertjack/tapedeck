"""The string a user actually types → the canonical 11-character video id.

`add` is the only door into the library, and everything past it is that id: the
entry directory, meta.json's `id`, every deep link the archive ever renders. So
the parsing happens exactly once, here, and it is strict — the four forms
SPEC-ingest-001 names and nothing else. Anything else is a usage error rather
than a fetch attempt, because a wrong guess costs a download and files a video
under a name no deep link will ever resolve.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
SITE = "youtube.com"
SHORT_HOST = "youtu.be"
SCHEMES = ("", "http", "https")
WATCH_PATH = "/watch"
SHORTS = "shorts"


class BadRequest(ValueError):
    """The target names no YouTube video."""


def canonical_url(video_id: str) -> str:
    """The watch URL for an id: what the fetcher is handed (a bare id is not
    something yt-dlp can resolve) and meta.json's url when the source names none.
    Same form as the deep links in contracts/library-layout.md."""
    return f"https://www.youtube.com/watch?v={video_id}"


def _host(url) -> str:
    host = (url.hostname or "").lower()
    return host.removeprefix("www.")


def _from_url(text: str) -> str | None:
    """The id a YouTube link carries, or None for a link that is not one."""
    try:
        # A scheme-less "youtu.be/<id>" is a path to urlsplit until it has an
        # authority marker; give it one so the host is read as a host.
        url = urlsplit(text if "//" in text else f"//{text}")
        host, path = _host(url), url.path
    except ValueError:  # malformed authority, e.g. an unclosed IPv6 bracket
        return None
    if url.scheme not in SCHEMES:
        return None
    parts = [part for part in path.split("/") if part]
    if host == SHORT_HOST:
        return parts[0] if len(parts) == 1 else None
    if host != SITE and not host.endswith(f".{SITE}"):
        return None
    if path.rstrip("/") == WATCH_PATH:
        return (parse_qs(url.query).get("v") or [None])[0]
    if len(parts) == 2 and parts[0] == SHORTS:
        return parts[1]
    return None


def video_id(target: str) -> str:
    """The canonical id in `target` — never a guess."""
    text = (target or "").strip()
    # The bare id is checked first because it is the one form with no structure to
    # read. Everything else must survive URL parsing: an 11-character path segment
    # on some other host ("example.com/not-a-video") is not an id, and looking for
    # a bare id *inside* an arbitrary string is exactly how it would become one.
    found = text if VIDEO_ID.fullmatch(text) else _from_url(text)
    if found and VIDEO_ID.fullmatch(found):
        return found
    raise BadRequest(
        f"{target!r} is not a YouTube video — expected a watch, youtu.be or shorts "
        "URL, or a bare 11-character video id"
    )
