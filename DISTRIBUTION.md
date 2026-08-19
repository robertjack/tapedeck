# Distribution status

**tapedeck is a live public project** as of 2026-08-19:
https://github.com/robertjack/tapedeck — MIT-licensed, CI green on every push.
This file tracks what's done and what remains between here and
`uv tool install tapedeck-cli` working for the whole world.

## Done

- **Public GitHub repo** with `origin` remote; history audited (gitleaks
  clean, no secrets, operator-specific paths untracked via CLAUDE.local.md).
- **License**: MIT (`LICENSE`, detected by GitHub, declared in pyproject).
- **CI**: `.github/workflows/evals.yml` runs the durable eval suite on
  `macos-latest` for every push and PR. Seam tools are faked by the evals'
  fixtures; ffmpeg is the one real-PATH dependency (doctor/setup check it
  genuinely) and the workflow installs it.
- **Package identity**: distribution `tapedeck-cli` (PyPI's `tapedeck` is an
  unrelated squatted project), executable `tapedeck`, version single-sourced
  in pyproject (`0.3.0`), full PyPI metadata (readme, license, urls,
  classifiers).
- **Docs for strangers**: README (user-facing), MANUAL (shipped in the wheel,
  `tapedeck help manual`), CONTRIBUTING (how the spec-first build works, what
  merges), and a commit gate that degrades gracefully on clones without the
  private harness.

## Remaining: publish to PyPI

Needs a PyPI account token (never stored in this repo):

```sh
uv build                      # sdist + wheel into dist/
UV_PUBLISH_TOKEN=... uv publish
```

Then smoke the public path from a machine (or empty uv cache) that has never
seen this repo:

```sh
uv tool install tapedeck-cli
tapedeck --version            # 0.3.0
tapedeck setup
```

Release cadence after that: bump `[project].version`, tag (`git tag v0.3.x &&
git push --tags`), `uv build && uv publish`.

## Later, if wanted

- **Homebrew tap** (`brew install robertjack/tap/tapedeck`) — the most natural
  channel for the Mac users this targets; worth doing once PyPI installs are
  proven.
- **GitHub release notes** per version, generated from the spec tickets.
