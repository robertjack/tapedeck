"""The string a user actually types → one canonical video id, or a collection.

`add` is the only door into the library, and everything past it is that id: the
entry directory, meta.json's `id`, every deep link the archive ever renders. So
the parsing happens exactly once, here, and it is strict — the forms
SPEC-ingest-001 and SPEC-ingest-002 name and nothing else. A wrong guess costs a
download and files a video under a name no deep link will ever resolve.

Two kinds of target come through the door. A watch, youtu.be or shorts URL — or
a bare id — names exactly one video, and still does when it carries a `list=`
parameter, because the fetch is `--no-playlist`. A playlist or channel URL
carries no video id of its own: it is a collection, and only the lister can say
what is in it.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
SITE = "youtube.com"
SHORT_HOST = "youtu.be"
SCHEMES = ("", "http", "https")
VIDEO = "video"
COLLECTION = "collection"
WATCH = "watch"
SHORTS = "shorts"
PLAYLIST = "playlist"
LIST_PARAM = "list"
# `youtube.com/<root>/<name>` — the channel spellings YouTube has accumulated.
CHANNEL_ROOTS = ("channel", "c", "user")
# A channel may be linked at one of its tabs; the tab is not part of its identity.
TABS = ("videos", "streams")


class BadRequest(ValueError):
    """The target names no YouTube video and no collection of them."""


def canonical_url(video_id: str) -> str:
    """The watch URL for an id: what the fetcher is handed (a bare id is not
    something yt-dlp can resolve) and meta.json's url when the source names none.
    Same form as the deep links in contracts/library-layout.md."""
    return f"https://www.youtube.com/watch?v={video_id}"


def _parse(text: str):
    """`(host, path segments, query)` for a URL-ish string, or None."""
    try:
        # A scheme-less "youtu.be/<id>" is a path to urlsplit until it has an
        # authority marker; give it one so the host is read as a host.
        url = urlsplit(text if "//" in text else f"//{text}")
        host = (url.hostname or "").lower().removeprefix("www.")
    except ValueError:  # malformed authority, e.g. an unclosed IPv6 bracket
        return None
    if url.scheme not in SCHEMES:
        return None
    return host, [part for part in url.path.split("/") if part], parse_qs(url.query)


def _youtube(host: str) -> bool:
    return host == SITE or host.endswith(f".{SITE}")


def _video(host, segments, query) -> str | None:
    """The id a link carries, or None for a link that carries none."""
    if host == SHORT_HOST:
        return segments[0] if len(segments) == 1 else None
    if not _youtube(host):
        return None
    if segments == [WATCH]:
        # `&list=` rides along on plenty of shared links; it names the playlist
        # the user happened to be in, not what they asked us to download.
        return (query.get("v") or [None])[0]
    if len(segments) == 2 and segments[0] == SHORTS:
        return segments[1]
    return None


def _collection(host, segments, query) -> bool:
    """Whether a link names a set of videos rather than one."""
    if not _youtube(host):
        return False
    named = segments[:-1] if len(segments) > 1 and segments[-1] in TABS else segments
    if named == [PLAYLIST]:
        return bool((query.get(LIST_PARAM) or [""])[0].strip())
    handle = len(named) == 1 and named[0].startswith("@") and len(named[0]) > 1
    return handle or (len(named) == 2 and named[0] in CHANNEL_ROOTS and bool(named[1]))


def resolve(target: str) -> tuple[str, str]:
    """`(VIDEO, id)` or `(COLLECTION, url)` for a target — never a guess."""
    text = (target or "").strip()
    # The bare id is checked first because it is the one form with no structure to
    # read. Everything else must survive URL parsing: an 11-character path segment
    # on another host ("example.com/not-a-video") is not an id, and hunting for a
    # bare id *inside* an arbitrary string is exactly how it would become one.
    if VIDEO_ID.fullmatch(text):
        return VIDEO, text
    parsed = _parse(text)
    if parsed:
        found = _video(*parsed)
        if found and VIDEO_ID.fullmatch(found):
            return VIDEO, found
        if _collection(*parsed):
            # A channel is not reducible to an id the way a video is, so the
            # lister gets the user's own URL — plus the scheme they may have left
            # off, since an external tool is going to have to fetch it.
            return COLLECTION, text if "//" in text else f"https://{text}"
    raise BadRequest(
        f"{target!r} is not a YouTube video or collection — expected a watch, youtu.be "
        "or shorts URL, a bare 11-character video id, or a playlist or channel URL"
    )


def video_id(target: str) -> str:
    """The canonical id of a target that names exactly one video."""
    kind, value = resolve(target)
    if kind == COLLECTION:
        raise BadRequest(
            f"{target!r} is a playlist or channel — ingest downloads exactly one video "
            "per invocation; expand it first and add the ids one at a time (`tapedeck "
            "add` does that for you)"
        )
    return value


def video_ids(text: str) -> list[str]:
    """A lister's stdout as ids: collection order, deduplicated, well-formed only.

    An external tool prints whatever it prints — a banner, a blank line, `NA` for
    an entry that has been taken down, the same video twice because it sits in
    the playlist twice. Anything that is not an id would become a library
    directory no deep link resolves, so only ids survive here.
    """
    found, seen = [], set()
    for line in text.splitlines():
        token = line.strip()
        if VIDEO_ID.fullmatch(token) and token not in seen:
            seen.add(token)
            found.append(token)
    return found
