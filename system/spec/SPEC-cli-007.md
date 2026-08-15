---
id: SPEC-cli-007
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-cli-005, SPEC-core-004]
---
`doctor` diagnoses this installation and changes nothing. It is the verb for the moment
`add` failed and the user cannot tell whether the fault is theirs, the machine's, or
tapedeck's: it prints what tapedeck needs, what it found, and what to do about the gap.

Its checks are **derived from the configuration seams** (SPEC-core-004), never from a
hardcoded list of tools. tapedeck has no opinion about which downloader or transcriber a
user runs, so `doctor` may not have one either — it knows only which seams must resolve
to something executable. Every command template in `config.toml` is checked by taking its
head executable — the first shell word of the command; a template built from pipeline or
`&&` stages may have every stage's head resolved, but the first always is — and resolving
that name on `PATH`. Swapping a seam to a different tool therefore changes what `doctor`
looks for, with no change here and no new clause. A seam whose head executable does not
resolve, or which is absent from `config.toml` altogether, is a **failure** for the
`[ingest]` and `[transcribe]` seams: there is nothing for `add` to run. The `[ask]` seams
are **optional** — `ask` needs them and `search` never does — so an unresolvable or
missing `[ask]` seam is reported as optional, with a reason saying which half of the tool
it costs, and never decides the exit code. The `[wiki]` maintainer seam is optional on
exactly that footing: `wiki.maintainer_command` unresolvable or missing costs the `wiki`
verbs that write and `add`'s auto-filing epilogue (SPEC-cli-009), and its reason says so,
while the four-stage chain runs without it and the exit code never turns on it.

Beyond the seams, `doctor` checks what the four-stage chain needs whatever tools fill it:
`ffmpeg` on `PATH`, because the downloader merges separate video and audio streams with
it; the library home resolvable and writable; SQLite FTS5 available in the running python,
without which there is no index; and the platform against the configured transcriber — if
that command names an Apple-Silicon-only MLX tool (`mlx_whisper`, `parakeet-mlx`) and this
machine is not arm64 macOS, that is a failure whose message says MLX needs Apple Silicon
and says the transcriber seam is one line of `config.toml` away from a tool that runs here.

The report is one aligned line per check: the check's name, its status — `pass`, `fail`,
or `optional` — and a short reason. The status begins at the same column on every line, so
the report skims as a column. A seam check is named by its dotted config key, so the
report reads as a map of the seams. The checks are emitted in a fixed order:
`ingest.fetcher_command`, `ingest.lister_command`, `transcribe.transcriber_command`,
`ask.librarian_command`, `ask.answerer_command`, `wiki.maintainer_command`, `ffmpeg`,
`home`, `fts5`, `platform` — every one of them always present, including the ones that
pass, because a diagnosis that prints only complaints cannot tell "checked and fine"
from "never looked". `--json` emits the same checks in the same order as
`[{check, status, detail}]`.

Exit 0 when no check failed, 1 otherwise; optional results never make it 1. `doctor`
touches the network never and runs no seam command — it resolves names on `PATH`, it does
not execute what it finds. It writes nothing beyond the first-run home scaffold every verb
creates, and it obeys the same TTY discipline as SPEC-cli-005: piped output carries no
escape sequences.
