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

## Installing on a new Mac

    uv tool install tapedeck
    tapedeck setup

`setup` is the first command of a new machine. It creates the library home
and tells you where it put it, then runs exactly the checks `doctor` runs
(§10) — but where `doctor` names the gap, `setup` names the command that
closes it here:

    transcribe.transcriber_command  fail  mlx_whisper: not on PATH
        uv tool install mlx-whisper
    ffmpeg                          fail  not on PATH
        brew install ffmpeg

Printing is all it does. Nothing is installed without your say-so:

    tapedeck setup          # what is missing, and what would fix it
    tapedeck setup --yes    # run those exact commands, then check again

Exit 0 when nothing required is missing — it says `ready` — and 1 when
something is. With `--yes` each printed command runs in turn, its output
streaming past as it goes, and then setup checks again and the second
report decides the exit code.

The remedies are yours too: they are a table in `config.toml` under
`[setup]`, one line per tool, `remedy.<tool> = '...'`. The defaults are
Homebrew and uv because that is a Mac; if you prefer MacPorts, pip, or a
tarball, edit the line and `--yes` runs yours. Homebrew missing gets said
first, with the one-liner that installs it — but setup never installs
Homebrew for you, no matter how many `--yes` you type. The `[ask]` seams
are optional, so `claude` is pointed at and never installed.

No model is downloaded here. When your transcriber is installed, setup
reminds you that the first transcription pulls the weights (~2.4GB for
parakeet). That wait belongs to your first `tapedeck add`, not to setup.

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
    [wiki]    maintainer_command   the agent that writes the wiki (§9)
    [wiki]    auto                 file each added video (default true)

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
If the wiki holds a page for the video, `rm` says so on stderr — the page
stays, and `tapedeck wiki lint` will keep naming it until you decide.
`--media-only` deletes just the video file(s): transcript, archive page,
and search keep working, at the cost of ever re-transcribing that video.
Videos are by far the biggest thing on disk, so a mature library can be
mostly knowledge.

### 9. The wiki: what you made of it

    tapedeck wiki file <id>
    tapedeck wiki sync [--dry-run]
    tapedeck wiki lint [--json]
    tapedeck wiki rebuild [--yes]
    tapedeck wiki tend [--yes]

The four stages end at an index that can find anything anyone said. The
wiki is the layer above that: what *you* know because of the videos — the
connection between two talks, the name you gave an idea, the second
thought a month later. It is written one video at a time by an agent
following your brief, and it compounds. Each filing is written against a
wiki that already holds everything filed before it, so a backlog swept in
upload order reads the way notes kept by someone watching all along would
read. Every other layer is disposable and re-derivable; this is the one
layer that can only be kept, which is why it lives in a git repository of
its own.

It is `wiki/` inside the library home, and it is plain markdown with
`[[wikilinks]]` — no database, no server, nothing only tapedeck can read.

File one video:

    tapedeck wiki file dQw4w9WgXcQ

The maintainer reads your brief and that video's archive page, then writes
and links whatever it decides the wiki needs. tapedeck does not review its
prose; it reviews the result — every wikilink resolves, every deep link
points at a real moment of a real video, the catalog names every page, the
source page cites its own recording, the log only grew. A filing that
fails any of those is rolled back whole and nothing half-written is left
behind. Accepted, it lands as one commit. Filing a video that already has
a page changes nothing and exits 0, so you never have to remember what you
filed.

File everything not yet filed:

    tapedeck wiki sync --dry-run    # the ids it would file, one per line
    tapedeck wiki sync              # file them, oldest video first

`sync` is that same operation in a loop over every video with media and an
archive page and no source page yet. Order is upload date, oldest first,
because the wiki accumulates and the order is part of what it becomes. One
video's failure never stops the sweep; the summary at the end counts
filed / already filed / skipped / failed, and a library that is fully
filed is a no-op that never wakes the agent at all.

Check that it still holds together:

    tapedeck wiki lint
    tapedeck wiki lint --json

`lint` is `doctor` (§10) one layer up: `doctor` asks whether this machine
can do the work, `lint` asks whether what the work produced is still true.
The gate judges a filing the moment it lands, but the wiki keeps living
after that — you rename a note, delete a page, edit a source page and take
its deep link with it, `rm` a video whose page is still standing. All of
that is allowed, and `lint` is how you ask the gate's questions of a wiki
nobody just wrote. It reads your working tree as it stands, hand edits
included, changes nothing, commits nothing, and needs no agent configured.
Every check prints, passes included:

    wikilinks   pass  47 links resolve
    citations   pass  every deep link verified
    index       fail  notes/agents.md is linked but does not exist
    unfiled     info  3 eligible videos have no page yet

`unfiled` and `orphans` are information and never fail: a wiki younger
than the library is not a broken wiki. Exit 0 when nothing failed, 1 when
something did.

Start the wiki over:

    tapedeck wiki rebuild            # what it would remove and refile
    tapedeck wiki rebuild --yes      # do it

Rewriting the brief, or swapping the maintainer for a better one, changes
the thing that produced every page you already have. `rebuild` is how you
get the wiki you would have had: it clears `sources/` and `notes/` in one
commit and then runs `sync` over the whole library again. Without `--yes`
it executes nothing and only prints — the resolved wiki path first, so a
surprising `$TAPEDECK_HOME` is visible before you agree to anything. This
is the one verb that destroys prose you may have typed yourself, which is
why it asks; and the wiki it replaces is still in the history, one
`git show` away, for as long as you keep the repository.

Let it read the whole wiki back to you:

    tapedeck wiki tend                 # read it, report only
    tapedeck wiki tend --yes           # let it act, under the same gate

`lint` catches what a rule can catch — a broken link, a page with no
citation. Some things about a wiki only a reader notices: two notes that
quietly disagree, a claim a later video already overtook, an idea that
keeps coming up in your filings and has never earned a page of its own.
`tend` is that reading, done by the same maintainer that writes the wiki,
over the whole of it — tapedeck stays the deterministic edge, and
everything between the edges is the agent's judgment, exactly as filing
already is.

Without `--yes` it only reports, in prose, to stdout:

    The zero-shot and few-shot notes both call themselves the "default"
    prompting approach — worth reconciling.
    "context window" is mentioned in three source pages and has no note
    of its own.
    sources/dQw4w9WgXcQ.md predates notes/rag.md, which looks like it
    supersedes the claim there about chunk size.

Whatever the agent wrote while forming that report is gone the moment it
exits: tapedeck resets the working tree unconditionally, so a report run
cannot change the wiki even if the agent tries to. Anything you had typed
and not committed is committed as `user edits` before that, so the reset
cannot take your writing with it. No commit of the tend itself, no log
entry — just the reading, on your screen.

`--yes` lets it act on what it finds — merge two notes, rewrite one, add
the page that was missing, retire one that's gone stale — then the whole
gate every filing passes judges the result: every wikilink resolves,
`CLAUDE.md` untouched, every deep link still pointing at a real moment of
a real video, the catalog and the log both still true. One rule belongs
to `tend` alone: nothing under `sources/` may be deleted or renamed,
because that page's existence is the wiki's only record that the video
was ever filed, and losing one would leave the next `sync` to refile it
as if it never happened. Notes are fair game for anything the maintainer
decides:

    tapedeck wiki tend --yes
    merged notes/zero-shot.md and notes/few-shot.md into notes/prompting.md
    added notes/context-window.md, linked from three source pages
    wiki tend committed

Run it after a batch of `add`s has settled, or whenever the wiki starts
reading like a pile of pages rather than the one thing you know.

The brief is your steering wheel. `wiki/CLAUDE.md` is scaffolded once with
defaults and is yours from then on: how notes are named and foldered, what
earns a page of its own, how long a source page runs, what taxonomy you
keep. tapedeck never rewrites it, and the maintainer is forbidden to touch
it — a filing that edited its own instructions is rejected on that alone.
Rewriting it wholesale is the intended end state, not a fault.

Filing happens automatically. Every `tapedeck add` that finishes files
that video, each one as it completes, so a channel sweep files as it
sweeps. It is an epilogue, not a stage: if the filing fails, or you never
configured a maintainer, `add` says so on stderr and is otherwise exactly
the command it always was — same exit code, same counts, same sweep. Turn
it off with one line in `config.toml`:

    [wiki]
    auto = false

Then the wiki changes only when you ask it to.

Read it in Obsidian. Point Obsidian at `wiki/` — "Open folder as vault" —
and the wikilinks, the backlinks and the graph all work with no
conversion, no import and no plugin. Any markdown editor does as well, and
so does `grep`. Edit by hand whenever you like: before it operates,
tapedeck commits whatever is pending as a `user edits` commit, so your
typing is already in the history and a rolled-back filing can never take
it along.

The repository is yours too. `wiki/` is nested inside nothing — not this
tool's repo, not the library's gigabytes of video — so `git log` reads as
the history of what you learned, and `git remote add` sends it wherever
you want without tapedeck knowing or caring.

### 10. When something is broken: doctor

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
    wiki.maintainer_command       optional  claude: not on PATH — filing needs it, lint does not

The `[ask]` seams and the wiki maintainer are the optional ones: without
them `ask` cannot run and nothing can be filed into the wiki — `add` skips
its automatic filing with a note, and `wiki lint` is answerable anyway —
but `add`, `search`, `list` and `show` do their work either way, so they
never fail the command. Exit 0 when nothing required failed, 1 when
something did. `--json` gives the same checks as `{check, status, detail}`
objects, in the same order, for scripting.

### 11. Advanced moves

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
    wiki file <id>                         file one video into the wiki
    wiki sync [--dry-run]                  file every video not yet filed
    wiki lint [--json]                     check the wiki still holds up
    wiki rebuild [--yes]                   clear it and refile from zero
    wiki tend [--yes]                      read the whole wiki, then act
    adapt-parakeet                         parakeet JSON -> whisper shape
    doctor [--json]                        check the seams and this machine
    setup [--yes]                          first run: scaffold, check, remedy
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
    wiki/                         your notes — markdown, its own git repo
    wiki/CLAUDE.md                the maintainer's brief — yours to rewrite
    wiki/index.md, wiki/log.md    the catalog and the chronology
    wiki/sources/<id>.md          one page per filed video
    wiki/notes/                   free-form pages, arranged by your brief

Troubleshooting (start with `tapedeck doctor`):

    add fails immediately, or "command not found"
        A seam points at a tool that isn't installed; doctor names it,
        and `tapedeck setup` prints the command that installs it.
    "the index could not be read ... run tapedeck reindex"
        The database predates a schema change; reindex is the migration.
    ask exits 1 refusing a citation
        Working as intended: the answer cited a moment that doesn't check
        out, and tapedeck would rather fail than show it to you.
    "unauthenticated requests to the HF Hub"
        Harmless parakeet noise (weights are cached); set HF_TOKEN to
        silence it.
    a wiki verb says the maintainer command is not set
        Filing needs an agent; `lint` does not. The default is scaffolded
        into config.toml with the other seams (§6); doctor reports it as
        optional, so nothing else in tapedeck is waiting on it.
    add noted that the wiki filing failed
        Only the filing failed, and it rolled itself back; the video is
        added, indexed and searchable. Run `tapedeck wiki sync` later,
        or set `[wiki] auto = false` (§9) to stop trying.
    a leftover video.part
        An interrupted download; the entry counts as having no video, and
        the next add fetches it fresh.
