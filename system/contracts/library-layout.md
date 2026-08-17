# Contract: the tapedeck library layout

**This is the conservation layer.** Every component reads or writes user data only
through this structure; changing it means coordinating every component and migrating
real libraries. Additive changes only.

## Location

`$TAPEDECK_HOME` if set, else `~/dev/storage/tapedeck`. The code repo never contains
user data.

```
$TAPEDECK_HOME/
  config.toml                  # user settings incl. tool-command seams (SPEC-core-004)
  library/<video-id>/          # one dir per video; <video-id> = 11-char YouTube id
    video.<ext>                # the downloaded video — THE source of truth
    meta.json                  # validates system/contracts/meta.schema.json
    transcript.json            # validates system/contracts/transcript.schema.json
  library/.fetching-<id>-*/    # ingest's staging dir: a download in flight, or a dead one
  archive/<video-id>.md        # human-readable render; regenerable from meta+transcript
  tapedeck.db                  # SQLite FTS index; regenerable from archive/ alone
  wiki/                        # markdown knowledge base, its own git repo — wiki-layout.md
```

## The staging directory

`ingest` downloads into `library/.fetching-<video-id>-<random>/` and installs the result
by renaming it, so that installing a finished video is one atomic operation rather than a
copy that can stop halfway. While a fetch is running, that directory is the fetch. If the
fetching process dies, it is left behind.

**It is tapedeck's own, and every reader of `library/` must be able to say so.** A
directory whose name is not a video id is not therefore a stranger's: the dot-prefixed
staging form is ours, it belongs to a download that is either in progress right now or
was interrupted, and the difference matters enormously to anyone deciding whether to
delete it. Describing one as "not tapedeck's" is how a live download gets removed by a
reader trying to tidy up — which is exactly what happened on 2026-08-16.

The grammar is **ingest's to publish and nobody else's to re-derive** (LESSON-0003).
Every component that walks `library/` and skips non-entries — cli's sweeps, wiki's
selection — asks ingest what it is looking at rather than pattern-matching the prefix
itself. Two components that each invented the same wrong sentence about it is the drift
that lesson exists to prevent, and agreeing with each other did not make either right.

## Write authority (exclusive, per SPEC-core-001)

| path | sole writer |
|---|---|
| `library/<id>/video.*`, `meta.json` | ingest |
| `library/<id>/transcript.json` | transcribe |
| `archive/*.md` | archive |
| `tapedeck.db` | index |
| `config.toml` | cli (created with defaults on first run; then user-owned) |
| `wiki/**` | wiki (sole tapedeck-side writer; the user co-authors by hand — `wiki-layout.md`) |

## Derivation chain (SPEC-core-002)

video → transcript → archive page → index rows. Every arrow is re-runnable; deleting
any derived artifact is recoverable by a CLI verb (`transcribe --force`, `reindex`).

## Deep links

A moment in a video is addressed as
`https://www.youtube.com/watch?v=<video-id>&t=<seconds>s` — used by search output and
ask citations.
