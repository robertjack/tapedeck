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
  archive/<video-id>.md        # human-readable render; regenerable from meta+transcript
  tapedeck.db                  # SQLite FTS index; regenerable from archive/ alone
  wiki/                        # markdown knowledge base, its own git repo — wiki-layout.md
```

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
