---
id: SPEC-cli-008
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-cli-005, SPEC-cli-007, SPEC-core-004]
---
`setup` is the first verb of a new machine: the one command a stranger runs after
installing tapedeck, before there is a library or a reason to trust that anything works.
`doctor` names the gap; `setup` names the gap **and the command that closes it here**.
It is one wizard with one hard rule: it installs nothing the user did not consent to.

It begins by scaffolding the library home — the same first-run scaffold every verb
performs, no more — and says where that home is, printing the resolved path so a
surprising `$TAPEDECK_HOME` is visible before anything else is discussed.

Then it checks. **`setup` reports exactly what `doctor` reports**: the same checks under
the same names, in the same fixed order (SPEC-cli-007), with the same statuses, the same
reasons, and the same required/optional split — from the same implementation, so a check
added to `doctor` appears in `setup` with no clause and no code here. `setup` may lay the
report out for a wizard rather than a column; it may not disagree with `doctor` about any
check, status, or reason.

For every **required** check that failed, `setup` prints the remedy. A failure that names
a missing executable — the seam checks and `ffmpeg` — gets the exact command that installs
that executable on this platform, on its own line, verbatim runnable, with nothing the
reader must substitute. A required failure that names no missing executable (`home`,
`fts5`, `platform`) carries `doctor`'s reason and says plainly that no install fixes it;
it still counts for the exit code. A missing executable the remedy table does not know is
named as missing, with the honest statement that tapedeck has no remedy for it.

The remedy table is a seam like every other (SPEC-core-004), keyed by executable name:
`[setup]` in `config.toml`, one line per tool, `remedy.<executable> = '<shell command>'`.
The user who installs by MacPorts, pip, or tarball edits a line and `--yes` runs theirs.
The defaults are written into the first-run `config.toml` with the rest, commented, and
they are macOS-centric because that is the platform tapedeck's published transcribers run
on: `remedy.yt-dlp = 'brew install yt-dlp'`, `remedy.ffmpeg = 'brew install ffmpeg'`,
`remedy.mlx_whisper = 'uv tool install mlx-whisper'`,
`remedy.parakeet-mlx = 'uv tool install parakeet-mlx'`, and for `claude` a pointer to
Claude Code's installation instructions. Every executable named by a head of the shipped
seam defaults, and `ffmpeg`, has an entry in the shipped table: a fresh install can always
be told what to do next.

Homebrew is the remedy behind the remedies. If any remedy `setup` is about to print begins
with `brew` and `brew` does not resolve on `PATH`, `setup` says that first — Homebrew is
missing, here is the bootstrap one-liner published at brew.sh — above the remedies that
need it, and with `--yes` it runs nothing at all and exits 1, because installing Homebrew
is the user's own deliberate step and not something a wizard does on their behalf.

An optional seam that does not resolve is optional exactly as `doctor` says it is: listed
apart from the required gaps, with its remedy shown as guidance, never deciding the exit
code, and **never executed**, not even with `--yes`.

**Consent is the specification.** Without `--yes`, `setup` executes nothing whatsoever: it
scaffolds, checks, prints, and stops. It exits 1 if any required check failed and 0
otherwise, and when nothing required failed it says the installation is `ready`, in that
word, so the answer is legible at a glance.

With `--yes` the user has said yes to the commands `setup` just printed, and to those
only. It runs each required remedy in turn through a shell, in the printed order, with the
command's own output streaming to stderr as it happens rather than captured and replayed;
a remedy that exits nonzero is reported and does not stop the ones after it. When the
remedies have run, `setup` runs the checks again — re-reading `config.toml` and
re-resolving `PATH`, because a remedy may have changed either — and prints the report a
second time. The exit code follows that second report.

`setup` never downloads a model. When the transcriber seam's head executable resolves, it
prints a single note that the first transcription downloads the model, in those words, and
names the approximate size where tapedeck publishes the transcriber and therefore knows it
(~2.4GB for `parakeet-mlx`) — a warning about a wait the user will meet on their first
`add`, and nothing that happens now. When the transcriber does not resolve there is no
such note: the remedy comes first.

Beyond the consented remedies, `setup` touches the network never, runs no seam command
(`doctor`'s rule holds: names are resolved on `PATH`, not executed), rewrites nothing
already in the home, and obeys the TTY discipline of SPEC-cli-005 — piped output carries
no escape sequences.
