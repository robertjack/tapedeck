# The Tapedeck Manual

A local video brain. `add` a YouTube URL and the video is downloaded,
transcribed on this machine, archived as readable markdown, and indexed —
then `search` finds the moment and `ask` answers questions with timestamped
deep links back into the videos. Everything lives in the library home
(default `~/Tapedeck`, a plain folder you can open) and nothing leaves your
machine except the download itself.

## How it works, in thirty seconds

Every video moves through a four-stage derivation chain:

    video  ->  transcript  ->  archive page  ->  search index

The downloaded video is the only source of truth — every later stage can be
regenerated from the one before it. Each stage is a plain file you can open:
the transcript is JSON, the archive page is markdown with clickable section
headings, the index is one SQLite database. Delete any derived file and a
verb rebuilds it.

Two commands are enough to start:

    tapedeck add <url>
    tapedeck ask "your question"

## SIDE A — GETTING STARTED

### 1. Add a video

    tapedeck add "https://www.youtube.com/watch?v=..."

Accepted forms: a full watch URL, youtu.be/ID, a shorts URL, or the bare
11-character id. A watch URL with a &list= parameter is treated as that one
video, never the whole playlist. Anything that isn't YouTube exits 2.

`add` runs the full pipeline: download, transcribe, render the archive page,
index it. Progress streams to stderr; when it finishes, the video is fully
searchable.

- Re-running is always safe: adding a video you already have skips the
  download and just refreshes the derived files.
- `--force` re-fetches one video from scratch, crash-safely: the copy
  already in your library stays intact until the replacement is fully in
  place.

### 2. Find a moment

    tapedeck search "agents" -k 2

Search is ranked full-text over the archive pages, one result per section,
each with its timestamp and a deep link that opens YouTube at that exact
moment. It stems English: "video" finds "videos", "transcribe" finds
"transcribing".

- `-k N` caps results (default 8).
- `--json` emits the same fields structurally.
- No matches is an answer, not an error: exit 0, empty output.

### 3. Ask the library

    tapedeck ask "what does Hodak say about ambition?"

The default mode is the librarian: a headless Claude agent is dropped into
your library home with read-only tools and a standing brief, reads whatever
it needs, and answers in prose with inline deep-link citations. Then
tapedeck verifies every citation mechanically — each link must point at a
video actually in your library, at a timestamp inside its real duration. A
fabricated citation fails the whole command (exit 1), so an answer you see
is an answer that checked out.

The librarian handles broad questions well: "what are these videos about?",
"where do two speakers disagree?".

Fast mode:

    tapedeck ask "how do long-running agents fail?" --fast -k 10

`--fast` skips the agent: top-k index chunks go to the answerer as numbered
excerpts, and tapedeck assembles the Sources section itself. Cheaper and
stricter — but it only finds words actually spoken in the videos, so it
suits lookup questions, not meta-questions. `-k` applies to fast mode only.

Scoping to one video:

    tapedeck ask "what's the 1% rule?" --video <id>

`--video` restricts either mode to a single video. In librarian mode the
citation check tightens to match: a citation to any other video — even one
in your library — is treated as fabrication. An unknown id exits 2.

Note: the librarian runs `claude -p` under your account, so it draws on
your Claude usage. Search never needs a model at all.

### 4. Browse what you have

    tapedeck list
    tapedeck show <id>

`list` is one line per video; `show` gives metadata and the archive path.
Both take `--json`. The archive pages themselves are worth opening in an
editor: readable markdown, one section per chapter, every heading a
clickable timestamp.

## SIDE B — POWER USE

### 5. Playlists and channels

    tapedeck add "https://www.youtube.com/playlist?list=..."
    tapedeck add "https://www.youtube.com/@somechannel/videos"

A playlist or channel URL expands to its videos and sweeps each one through
the standard pipeline, in order. The sweep is built for repetition:

- Already-complete videos are skipped entirely — re-running a channel URL
  is the idempotent way to pick up new uploads.
- One failure never stops the sweep: it is reported to stderr, the rest
  continue, and the summary at the end counts added / skipped / failed.
  Exit 1 only if something failed.
- `--force` on a collection is refused (exit 2) — re-fetching an entire
  channel must be deliberate, one video at a time.

### 6. The config seams

Every external tool sits behind a one-line command template in
`config.toml` in the library home. Change the line and tapedeck uses the
new tool — no code changes, ever. The file is scaffolded once and then it
is yours.

    [ingest]  fetcher_command      downloads one video (yt-dlp, h264 <=1080p)
    [ingest]  lister_command       expands a playlist/channel to video ids
    [transcribe] transcriber_command   audio -> timestamped segments
    [transcribe] model             the label stamped on every transcript
    [ask]     librarian_command    the default ask agent
    [ask]     answerer_command     the --fast answerer

Each seam runs as a shell command with its inputs in environment variables,
documented in comments above each line.

### 7. Model upgrades: retranscribe

Every transcript records which model made it. When the configured
`[transcribe] model` label differs from a transcript's label, that video is
superseded — and one verb re-derives it:

    tapedeck retranscribe --dry-run    # list what would be redone
    tapedeck retranscribe              # re-transcribe, re-render, re-index

The upgrade recipe: edit `transcriber_command` and `model` in config.toml
(a new model deserves a new label), dry-run to see the blast radius, then
run it. Failures don't stop the sweep; run it again and it converges — a
run with nothing left to do exits 0 having done nothing. Entries the sweep
could never re-derive (media reclaimed by `rm --media-only`, stray
directories) are noted on stderr and skipped.

`adapt-parakeet` is the small filter that makes the parakeet transcriber
seam possible: parakeet JSON on stdin, whisper-shaped JSON on stdout. You
will only meet it inside `transcriber_command`.

### 8. Disk and removal

    tapedeck rm <id>                # forget the video everywhere
    tapedeck rm <id> --media-only   # keep the knowledge, reclaim the disk

Plain `rm` removes the library entry, the archive page, and the index rows.
`--media-only` deletes just the video file(s): transcript, archive page,
and search keep working, at the cost of ever re-transcribing that video.
Videos are by far the biggest thing on disk, so a mature library can be
mostly knowledge.

### 9. When something is broken: doctor

    tapedeck doctor
    tapedeck doctor --json

`doctor` reads your setup and reports; it changes nothing, downloads
nothing, and runs none of the tools it asks about — it only checks that
they are there. Run it when `add` failed and you cannot tell whether the
problem is your machine, your config, or tapedeck.

The list of things it checks is not a list at all: it is read off your
`config.toml`. For every seam in §6 it takes the first word of the command
— the executable — and looks for it on your `PATH`. Point
`transcriber_command` at a different tool and `doctor` starts checking for
that tool instead. Then it checks the few things the derivation chain needs
whatever tools you fill it with: `ffmpeg` (the downloader merges the video
and audio streams with it), that the library home resolves and is
writable, that this python has SQLite FTS5 (no FTS5, no index), and that
your transcriber can actually run here — an MLX transcriber on anything
but an Apple Silicon Mac is a fail, and the fix is one line of config.

Every check prints, passes included, so you can tell "checked and fine"
from "never looked":

    ingest.fetcher_command        pass      yt-dlp
    transcribe.transcriber_command fail     mlx_whisper: not on PATH
    ask.librarian_command         optional  claude: not on PATH — ask needs it, search does not

The `[ask]` seams are the only optional ones: without them `ask` cannot
run, but `add`, `search`, `list` and `show` are untouched, so they never
fail the command. Exit 0 when nothing required failed, 1 when something
did. `--json` gives the same checks as `{check, status, detail}` objects,
in the same order, for scripting.

### 10. Advanced moves

Move the library — the home is `~/Tapedeck` unless `$TAPEDECK_HOME` says
otherwise. It is resolved on every run, so pointing it at an external disk
or a second, separate library is one variable; first use scaffolds a fresh
home there:

    TAPEDECK_HOME=~/decks/cooking tapedeck add "https://youtu.be/..."

Check the install — `tapedeck --version` prints the installed version and
nothing else. It touches no library, so it is the safe first thing to run
on a new machine:

    tapedeck --version

Tune the librarian — its standing instructions live in `CLAUDE.md` in the
library home. It is your file: add house style, preferred answer length,
context about what the library is for.

A shell one-liner:

    brain() { tapedeck ask "$*"; }

Disaster recovery — nothing derived is precious:

    lost tapedeck.db        ->  tapedeck reindex
    lost an archive page    ->  tapedeck add <id>
    lost a transcript       ->  tapedeck retranscribe
    lost a video file       ->  tapedeck add <id> --force

## REFERENCE

Verbs:

    add <url> [--force]                    fetch, transcribe, archive, index
    search <query> [-k N] [--json]         stemmed, timestamped excerpts
    ask <question> [--fast] [-k N] [--video <id>]   cited answers
    list [--json]                          one line per video
    show <id> [--json]                     metadata + archive path
    reindex                                rebuild tapedeck.db from archive/
    rm <id> [--media-only]                 remove, or reclaim disk only
    retranscribe [--dry-run]               re-derive superseded transcripts
    adapt-parakeet                         parakeet JSON -> whisper shape
    doctor [--json]                        check the seams and this machine
    help [<verb> | manual]                 this manual, in tiers

Global options:

    --version                              the installed version, then exit
    -h, --help                             terse usage for any verb

Exit codes:

    0   success (including "no results" and "nothing to do")
    1   operation failure (fetch/transcribe/answer failed, citation refused)
    2   usage or validation error (bad URL, unknown id, refused flag)

What's where (in the library home):

    library/<id>/video.<ext>      the download — the only source of truth
    library/<id>/meta.json        title, channel, date, duration, chapters
    library/<id>/transcript.json  timestamped segments + the model label
    archive/<id>.md               the readable page, deep-linked headings
    tapedeck.db                   the search index — fully disposable
    config.toml, CLAUDE.md        the seams and the librarian's brief

Troubleshooting (start with `tapedeck doctor`):

    add fails immediately, or "command not found"
        A seam points at a tool that isn't installed; doctor names it.
    "the index could not be read ... run tapedeck reindex"
        The database predates a schema change; reindex is the migration.
    ask exits 1 refusing a citation
        Working as intended: the answer cited a moment that doesn't check
        out, and tapedeck would rather fail than show it to you.
    "unauthenticated requests to the HF Hub"
        Harmless parakeet noise (weights are cached); set HF_TOKEN to
        silence it.
    a leftover video.part
        An interrupted download; the entry counts as having no video, and
        the next add fetches it fresh.
