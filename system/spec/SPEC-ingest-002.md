---
id: SPEC-ingest-002
type: requirement
component: ingest
status: active
depends: [SPEC-ingest-001, SPEC-core-004]
---
Some URLs name a collection of videos rather than one video: a playlist URL
(`youtube.com/playlist?list=ID`) or a channel URL (`youtube.com/@handle`,
`youtube.com/channel/ID`, `youtube.com/c/NAME`, `youtube.com/user/NAME`, each with or
without a trailing `/videos` or `/streams` path). A watch/short/youtu.be URL is always
a single video, even when it carries a `list=` parameter (`--no-playlist` semantics,
SPEC-ingest-001) — only URLs with no video id of their own are collections.

`expand <url>` resolves any accepted URL to video ids on stdout, one per line: a
single-video form prints its one canonical id without invoking any external tool; a
collection URL invokes the configured lister and prints the collection's video ids in
collection order, deduplicated, filtered to well-formed 11-character ids. A URL that is
neither a video nor a collection exits 2; a failed lister exits 1 and prints nothing to
stdout. `add <url>` on a collection URL exits 2 and says to use the collection path —
ingest downloads exactly one video per invocation.

The lister is a config seam like the fetcher (SPEC-core-004): `[ingest].lister_command`
runs as a shell command with env `$TAPEDECK_COLLECTION_URL` and must print video ids
one per line on stdout. The component publishes its default lister command (scaffolded
into `config.toml` on first run), verbatim:
`yt-dlp --flat-playlist --print "%(id)s" "$TAPEDECK_COLLECTION_URL"`.
