---
id: SPEC-ingest-004
type: requirement
component: ingest
status: active
depends: [SPEC-ingest-001, SPEC-core-004]
---
The fetcher's chatter is captured, not streamed — and replayed the moment it matters.
Today `add` relays the download tool's every line: yt-dlp alone prints dozens of
carriage-return progress fragments per video, and the one line ingest itself owns is
buried in them. After this clause, the fetcher subprocess's output (stdout and stderr
both) is **captured** by ingest and, on a clean exit, discarded: the tool spoke to
nobody, and the pipeline's own lines are the story of the add.

**Progress comes from the filesystem, not from parsing the tool.** While the fetcher
runs, ingest reports on its own stderr what has observably happened: the bytes landed
so far in the staging directory, refreshed every few seconds, only while the tool is
running — a handful of lines for a typical download, never a firehose. When the tool
exits clean, one closing line accounts for the total. The staging directory is
ingest's own (SPEC-ingest-003), so watching it grow is tool-agnostic by construction:
swap yt-dlp for anything else through the seam and the progress report neither breaks
nor needs to be taught the new tool's output format.

**A failing fetch replays everything.** When the fetcher exits nonzero, the captured
output is written to stderr in full — byte for byte, before the existing failure
line — because the tool's own words are the diagnosis. The production incident this
preserves: a 2026-08-17 DRM 403 (LESSON-0006) was diagnosable *only* from yt-dlp's
raw output. Quiet means quiet on success; a failure has never been louder.

**`add --verbose` streams raw, as today.** The boundary gains the flag: with it, the
fetcher's output passes straight through as it always has, no capture and no
heartbeat — the user asked to watch the tool itself. Without it, the discipline above
is the default. `expand`'s lister is already captured (its stdout *is* the answer)
and is untouched; so are the staging rename, the skip/--force rules, and everything
else SPEC-ingest-001 and SPEC-ingest-003 pin.
