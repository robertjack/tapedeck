---
id: SPEC-cli-013
type: requirement
component: cli
status: active
depends: [SPEC-cli-007, SPEC-cli-008, SPEC-cli-012, SPEC-ingest-004]
---
The tools rot on a schedule the user does not control, and `setup` learns to say so.
YouTube broke the fetcher twice in one week (LESSON-0001, LESSON-0006), and both times
the whole fix was "update the tool" — a command a semi-technical user does not know
and should not have to. Two clauses, both in `setup`'s existing consent shape and
`add`'s existing failure shape; nothing installs, updates, or runs without being
printed first and agreed to.

**`setup --refresh`.** Where plain `setup` names what is *missing* and the remedy
that installs it, `setup --refresh` names what is *present* and the command that
updates it: one line per seam tool that resolves on PATH, the update command drawn
from `[setup].update.<executable>` exactly the way remedies are drawn from
`[setup].remedy.<executable>` — the scaffold writes brew/uv defaults beside the
remedy table, an absent key reads as the shipped default (one default, written down,
the code agreeing with what it wrote — SPEC-cli-009's rule), and a user who prefers
another package manager edits the line. Printing is all `--refresh` does;
`--refresh --yes` runs each printed command in turn, output streaming, then re-runs
the checks, and the second report decides the exit code, exactly as `--yes` alone
already behaves. Tools that do not resolve are the plain wizard's business, not the
refresher's: `--refresh` updates what exists, it never installs what does not.

**A failed fetch says where the explanations live.** When a video's pipeline fails at
the ingest stage inside `add`, the cli's existing error line gains one sentence: the
download tool's own output is replayed above it (SPEC-ingest-004 already guarantees
that), and `tapedeck help manual` explains the common causes while
`tapedeck setup --refresh` updates the tool that most often is one. This sentence is
the cli's, in the cli's vocabulary about its own surface — ingest still knows nothing
about verbs, manuals, or package managers, and its own failure line is untouched.
The most common terminal moment a new user will ever hit — a 403 from a platform that
churns monthly — now ends with the two commands that resolve it instead of a raw exit
code, and `MANUAL.md`'s reference entry for that failure names `--refresh` too.
