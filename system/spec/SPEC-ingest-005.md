---
id: SPEC-ingest-005
type: requirement
component: ingest
status: active
depends: [SPEC-ingest-001, SPEC-core-002, SPEC-core-004]
---
A video does not have to come from YouTube. `add <path>` accepts a path to a media file
that already exists on this machine — a lecture capture, a meeting recording, footage
someone sent you — and puts it in the library beside everything fetched from the
network. Everything downstream keys on a video id and a transcript, neither of which knows
where a video came from, so most of the system needs nothing new. The exceptions are
the two places that address a *moment* rather than a video, and they follow the layout
contract's one deep-link rule rather than growing a second: the archive builds a page's
addresses from the video's own url (SPEC-archive-001), and ask resolves and verifies a
local citation exactly as it does a YouTube one (SPEC-ask-001), which the wiki's gate
consumes rather than re-deriving (SPEC-wiki-002).

**Resolution.** `resolve` answers `(VIDEO, <id>)` for a target naming an existing file,
before it considers YouTube at all; a target that is neither an existing path nor a
YouTube URL still raises the same usage error it raises today. Deciding this is
ingest's alone — it publishes the id grammar and what counts as a video (LESSON-0003),
and the cli routes on what it answers without learning a second rule.

**The id is a digest of the file's contents**, eleven characters of the library
layout's alphabet, and nothing else: not the path, not the name, not the modification
time. Two consequences are the point rather than side effects. The same footage added
twice is one entry and the second add is the ordinary skip of SPEC-ingest-001, even if
it was renamed or moved between the two. And a file that is edited is different footage
with a different id, rather than a silent overwrite of the entry the old one made.

**The library references the file; it does not copy it.** The entry's `video.<ext>`
is a symlink to the path given. Copying would double the disk cost of every local
video for no gain the derivation chain can use, while a link satisfies every rule
already written: transcribe reads through it, the entry holds a video for
SPEC-ingest-001's skip, and `rm` removes the link rather than the user's own file.
It also degrades the way the system already understands. If the original is moved or
deleted the link dangles, the entry reads as holding no video exactly as
`rm --media-only` leaves one (SPEC-cli-002) — transcript, archive page and index rows
all stand, only re-transcription is unavailable — and re-adding the file at its new
path repairs the entry under the same id.

**Metadata is what the file can honestly say about itself.** `title` is the filename
without its extension; `upload_date` is the file's modification date, the closest thing
to when this footage came into being; `channel` is empty, because a local file has no
publisher and inventing one would put a fiction in the archive's byline; `url` is the
`file://` URL of the path, which is what makes the layout contract's deep-link rule
address a local moment without a second rule. `duration_s` is read from the media file
itself with `ffprobe`, and an add whose duration cannot be read fails cleanly with no
partial entry rather than recording a zero: every citation this system verifies is
checked against that number, so a guess would launder itself into evidence. ffprobe is
not a new dependency and does not become a seam — it ships with the ffmpeg the pipeline
already requires and `doctor` already checks, and a second command template for the
same install would be config surface without a decision behind it.

The fetcher seam is not involved: there is nothing to download, so
`[ingest].fetcher_command` is neither read nor run, and a machine with no fetcher
configured can still add local files. Staging and installation are unchanged — the link
and metadata are assembled in the staging directory of SPEC-ingest-003 and installed by
rename — so an interrupted local add leaves no half-made entry, exactly like an
interrupted download.
