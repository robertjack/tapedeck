---
id: SPEC-cli-010
type: requirement
component: cli
status: active
depends: [SPEC-cli-007, SPEC-core-004, SPEC-ingest-003]
---
`doctor` resolves a seam's executable the way a shell would, and describes a staging
directory the way ingest does.

**The executable.** A seam command is a shell command (SPEC-core-004), and a shell command
may begin with environment assignments — `VAR=value cmd args` sets `VAR` for `cmd` and
runs `cmd`. `doctor` currently takes the first shell word as the program, so the user's
own configured transcriber:

    HF_HUB_OFFLINE=1 parakeet-mlx --output-format json ...

is diagnosed as `HF_HUB_OFFLINE=1: not on PATH`, and `doctor` has reported one failed
check on a working installation ever since that line was configured. A health check that
cries wolf about a seam that runs perfectly is worse than one that stays quiet: it teaches
the user to skim past the one row that will one day matter. So the head of a command is
the first word that is **not** a `NAME=value` assignment, and the row names that program.

Note what this does not become: a shell. `doctor` still reports on one program per seam
and still does not chase `&&`, pipes or subshells (SPEC-cli-007's reasoning is unchanged —
the first head is the one that always has to resolve). Skipping assignments is not
following control flow; it is reading the same first command the shell would.

**The staging directory.** Where `add`'s collection sweep walks `library/` and passes over
an entry, it asks ingest what it is looking at (SPEC-ingest-003) rather than deciding from
the name itself, and it never calls a staging directory of ours foreign. What it says
instead is the user's business and this clause fixes only the falsehood: the note must
make clear the directory belongs to a tapedeck download rather than to a stranger, so that
nobody reads a skip line as permission to delete a fetch in progress.
