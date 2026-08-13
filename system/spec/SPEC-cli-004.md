---
id: SPEC-cli-004
type: requirement
component: cli
status: active
depends: [SPEC-cli-001, SPEC-transcribe-001, SPEC-core-002]
---
`retranscribe [--dry-run]` is SPEC-core-002's "better model regenerates its whole
layer" made a verb: it sweeps the library for videos whose `transcript.json` model
label differs from the configured `[transcribe].model` and regenerates their derived
chain — transcribe `--force`, then archive render and index update. `--dry-run` prints
the ids that would be redone, one per line, and changes nothing. Videos already
labelled with the configured model are untouched. One video's failure doesn't stop the
sweep (report to stderr, summary at the end, exit 1 if anything failed); with every
label current the sweep is a no-op exiting 0.

`adapt-parakeet` exposes transcribe's `from-parakeet` filter (SPEC-transcribe-002) on
the installed surface — stdin to stdout, exit codes passed through — so the documented
parakeet transcriber command works wherever tapedeck is installed, with no assumption
about which python is on PATH. The first-run `config.toml` scaffold documents that
parakeet alternative in a comment beside the whisper default, exactly as
SPEC-transcribe-002 publishes it.
