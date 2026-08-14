---
id: SPEC-ingest-001
type: requirement
component: ingest
status: active
depends: [SPEC-core-003, SPEC-core-004]
---
`add <url>` accepts any of: a full watch URL (`youtube.com/watch?v=ID`), a short URL
(`youtu.be/ID`), a shorts URL (`youtube.com/shorts/ID`), or a bare 11-character video
id — and extracts the canonical id, rejecting anything else with exit 2. It invokes the
configured fetcher, which must produce `library/<id>/video.<ext>` plus metadata; ingest
writes `library/<id>/meta.json` validating `system/contracts/meta.schema.json`
(chapters included when the source provides them). If the video directory already
exists with a video file and meta.json, the fetch is skipped unless `--force`. A failed
fetch leaves no partial `library/<id>/` behind.

A `--force` re-fetch never risks the copy already in the library. The fetch is staged
inside the library home, hidden from readers (a dot-prefixed path, which components
already skip), so the finished video reaches its entry by a rename on the library's own
filesystem rather than a copy across devices that can stop halfway. The video already in
the entry stays intact until its replacement is fully in place. However a forced
re-fetch fails — the fetcher errors or dies mid-write, the metadata does not validate,
the install cannot finish — the entry is left as it was: the old video byte-identical
beside its old `meta.json`, still usable. An entry never holds a partially written video
that later reads as complete.

ingest owns two pieces of vocabulary the rest of the system reads, and publishes them
for its callers rather than leaving each to re-derive its own copy (LESSON-0003): the
canonical id grammar, and what counts as a downloaded video. `library/<id>/video.<ext>`
is the download only when `<ext>` names a container — the suffixes a fetcher leaves
mid-flight or beside the video (`.part`, `.ytdl`, `.temp`, `.tmp`, `.json`,
`.description`, and image suffixes) are never the video. An entry holding only
`video.part` therefore has no video: the next `add` re-fetches it, and every other
component reaches that same verdict because it consumes ingest's rule instead of
writing its own.

The component publishes its default fetcher command (the value the cli scaffolds into
`config.toml` on first run, per SPEC-core-004), and that default is the battle-tested
shape of LESSON-0001, verbatim:
`yt-dlp --no-playlist --write-info-json -f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" -o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"`.
