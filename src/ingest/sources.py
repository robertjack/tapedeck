"""What a target names: one video, a collection of them, or nothing we can act on.

This is the canonical id grammar of the whole system (SPEC-ingest-001). Any
component that has to ask "is this a video id?" imports the answer from here
rather than writing the regular expression again — a second copy is the defect
even while it still agrees (LESSON-0003).

The split between a video and a collection is decided by the URL alone
(SPEC-ingest-002): a watch, shorts or youtu.be URL is one video even when it
carries a `list=` parameter, because that is what `--no-playlist` means. Only a
URL with no video id of its own — a playlist, a channel — names a collection,
and only those are worth asking an external lister about.

A target naming a file that already exists on this machine is a video too
(SPEC-ingest-005), and `resolve` checks the filesystem before it parses anything
as a URL at all. Its id is not YouTube's: it is a digest of the file's own
contents, so the same footage is the same entry however it is named or moved,
and editing the footage is honestly a different video.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ID_LENGTH = 11
VIDEO_ID = re.compile(rf"[A-Za-z0-9_-]{{{ID_LENGTH}}}")
VIDEO = "video"
COLLECTION = "collection"

SCHEMES = ("", "http", "https")
SITE = "youtube.com"
SHORT_HOST = "youtu.be"
HOST_PREFIXES = ("www.", "m.", "music.")
WATCH, SHORTS, PLAYLIST = "watch", "shorts", "playlist"
VIDEO_PARAM, LIST_PARAM = "v", "list"
CHANNEL_ROOTS = ("channel", "c", "user")
HANDLE = "@"
# a channel or playlist URL may end on one of its tabs and still name the same
# collection: /@handle and /@handle/videos are asked of the lister identically
TABS = ("videos", "streams")


class BadRequest(ValueError):
    """The target is neither a video nor a collection — a usage error (exit 2)."""


def canonical_url(video_id: str) -> str:
    """The one URL shape tapedeck hands to external tools and writes into meta."""
    return f"https://www.youtube.com/watch?v={video_id}"


def local_target(target: str) -> Path | None:
    """The absolute path `target` names, if it is a file that already exists on
    this machine — checked before `target` is considered as a YouTube URL at all
    (SPEC-ingest-005). None for anything that is not an existing file, including
    a bare relative name that happens to parse as a URL segment.

    Resolved (symlinks and relative components followed) here, once, so every
    later step — hashing, the symlink target, the file:// url — addresses the
    same real path.
    """
    text = (target or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path.resolve() if path.is_file() else None


def local_id(path: Path) -> str:
    """A deterministic digest of the file's own contents — not its path, name,
    or modification time — so the same footage added twice, however it was
    renamed or moved, lands as the same entry, and edited footage is honestly a
    different one. The layout's id alphabet is exactly base64url's, so the
    digest needs no re-encoding to fit it.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return base64.urlsafe_b64encode(digest.digest()).decode("ascii")[:ID_LENGTH]


def resolve(target: str) -> tuple[str, str]:
    """`(VIDEO, id)` or `(COLLECTION, url)`. Raises BadRequest on anything else.

    A file already on this machine wins first and unconditionally: it needs no
    network round trip and no YouTube grammar to be a video. The collection case
    keeps its URL rather than an id of its own: the lister seam is told where to
    look, and every channel form points at the same place.
    """
    text = (target or "").strip()
    local = local_target(text)
    if local is not None:
        return VIDEO, local_id(local)
    if VIDEO_ID.fullmatch(text):
        return VIDEO, text
    host, segments, query = _parse(text)
    if not _youtube(host):
        raise BadRequest(f"{target!r} is not a YouTube URL")
    found = _video(host, segments, query)
    if found:
        return VIDEO, found
    if _collection(host, segments, query):
        return COLLECTION, text
    raise BadRequest(f"{target!r} names no local file, YouTube video, playlist or channel")


def video_id(target: str) -> str:
    """The canonical id of a single-video target, for callers that accept no other
    kind — `add` downloads exactly one video per invocation."""
    kind, value = resolve(target)
    if kind != VIDEO:
        raise BadRequest(
            f"{target!r} names a collection, not one video — expand it first "
            "(`ingest expand <url>`, or `tapedeck add <url>` to sweep it)"
        )
    return value


def video_ids(text: str) -> list[str]:
    """The well-formed ids in a lister's output, in order, without repeats. A
    listing is another program's stdout: it may carry blank lines, notices, or the
    same video twice, and none of that should reach the library."""
    found: list[str] = []
    for line in (text or "").splitlines():
        token = line.strip()
        if VIDEO_ID.fullmatch(token) and token not in found:
            found.append(token)
    return found


def _parse(text: str) -> tuple[str, list[str], dict]:
    """Host (normalized), path segments, query. Anything urlsplit cannot read is a
    bad request, not a crash — this runs on whatever the user typed."""
    try:
        parts = urlsplit(text)
        if parts.scheme.lower() not in SCHEMES:
            raise BadRequest(f"{text!r} is not an http(s) URL")
        if not parts.netloc:  # a URL written without its scheme: youtu.be/<id>
            parts = urlsplit("//" + text)
        host, path, query = (parts.hostname or ""), parts.path, parts.query
    except ValueError as exc:  # a malformed netloc, e.g. an unclosed IPv6 literal
        raise BadRequest(f"{text!r} is not a URL: {exc}") from exc
    return _site(host), [s for s in path.split("/") if s], parse_qs(query)


def _site(host: str) -> str:
    """The host without the subdomains that mean the same site: www, m, music."""
    host = host.lower()
    for prefix in HOST_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _youtube(host: str) -> bool:
    return host in (SITE, SHORT_HOST)


def _first(query: dict, key: str) -> str:
    values = query.get(key) or [""]
    return values[0].strip()


def _id(candidate: str) -> str | None:
    return candidate if VIDEO_ID.fullmatch(candidate) else None


def _short(host: str) -> bool:
    """youtu.be — the host that carries the id in its path, and never a collection."""
    return host == SHORT_HOST


def _video(host: str, segments: list[str], query: dict) -> str | None:
    """The three single-video URL shapes, plus their scheme-less spellings."""
    if _short(host):
        return _id(segments[0]) if len(segments) == 1 else None
    if segments == [WATCH]:
        return _id(_first(query, VIDEO_PARAM))
    if len(segments) == 2 and segments[0] == SHORTS:
        return _id(segments[1])
    return None


def _collection(host: str, segments: list[str], query: dict) -> bool:
    """A playlist, or a channel in any of the spellings YouTube hands out."""
    if _short(host) or not segments:
        return False
    if segments[0] == PLAYLIST:
        return len(segments) == 1 and bool(_first(query, LIST_PARAM))
    if segments[0].startswith(HANDLE) and len(segments[0]) > 1:
        return _tab_only(segments[1:])
    if segments[0] in CHANNEL_ROOTS:
        return len(segments) >= 2 and bool(segments[1]) and _tab_only(segments[2:])
    return False


def _tab_only(rest: list[str]) -> bool:
    return not rest or (len(rest) == 1 and rest[0] in TABS)
