# Contributing

Thanks for looking under the hood. This repo works differently from most, and
knowing how will save you time.

## How this codebase is built

**`system/` is the real codebase; `src/` is generated output.** Every module
under `src/` was produced by a code-generation harness working from the
specifications, contracts, and tests in `system/` — and gets regenerated
wholesale when those change. The harness itself is a private tool that isn't
published (yet), which has one big consequence for contributors:

**Hand-edits to `src/` can't be merged.** Not as a style preference — the next
regeneration would silently erase them. The durable, reviewable, contributable
layer is everything else:

## What contributions land

- **Bug reports** — especially with the failing command's full output.
  `tapedeck add` replays its download tool's output on failure precisely so
  reports can include it.
- **Eval additions** — a failing test in `system/evals/` that demonstrates a
  real defect is the single most useful artifact you can send. The suite runs
  with `just eval-all` (pytest; no network, no private tools, fakes injected
  through config seams) and CI runs it on macOS for every push.
- **Spec issues** — if behavior seems wrong, the argument belongs against the
  clause in `system/spec/` that pinned it (or the clause that's missing).
- **Docs** — `README.md` and `MANUAL.md` are hand-maintained and PRs to them
  merge normally, as does packaging (`pyproject.toml`) and CI.

## The commit hook

`lefthook.yml` carries a provenance gate used by the maintainer's tooling. If
you run `lefthook install` without that tooling on your PATH, the gate skips
itself with a note — your commits work normally.

## The paper trail

`system/provenance/` and the `Phx-*` commit trailers are the generation
history — which spec state produced which code, at what cost. They're
documentation of how this repo was actually built, and they're append-only:
please don't edit them in PRs.
