<!--
  Before you spend time on a diff: `src/` is generated from `system/`, and a
  regeneration will erase hand-edits to it. Changes land in the durable layer,
  the docs, or the packaging instead. See CONTRIBUTING.md.
-->

## What this changes

<!-- One paragraph. What is different afterwards, and for whom. -->

## Why

<!-- The reasoning. If this changes behavior, the argument belongs in a spec
     clause under system/spec/ as well as here. -->

## Layer

<!-- Tick what this touches. -->

- [ ] `system/spec/` — a behavioral constraint
- [ ] `system/evals/` — tests driving a component's command-line boundary
- [ ] `system/contracts/` or `system/lessons/` — shared vocabulary, or a durable finding
- [ ] Docs (`README.md`, `MANUAL.md`, `CONTRIBUTING.md`)
- [ ] Packaging / CI
- [ ] `src/` — **can't be merged**; a regeneration will overwrite it

## Checks

- [ ] `just eval-all` passes locally
- [ ] If a user-facing verb or flag moved, `MANUAL.md` says so (a test pins this)
