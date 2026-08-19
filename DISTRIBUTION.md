# Distribution prep

This is a checklist, not a plan already put into motion — nothing has been
published anywhere. No git remote is configured and no package has been
uploaded. Everything below is either already done in-repo, or is an open
decision with the exact commands to run once the decision is made.

## Already done

- **CI**: `.github/workflows/evals.yml` runs the durable eval suite
  (`system/evals`) on `macos-latest` for every push and PR, via `uv run
  --with pytest pytest system/evals -q`. The seam tools (yt-dlp, ffmpeg,
  mlx_whisper, etc.) are faked by the evals' fixtures, so the CI job needs
  no `brew install` steps.
- **Versioning**: `pyproject.toml` `[project].version` is the single source
  of truth (currently `0.2.0`); `tapedeck --version` reads it back out of
  installed distribution metadata (SPEC-cli-006).
- **Doctor / setup**: `tapedeck setup` (`src/cli/setup.py`) is the
  first-run wizard — it creates the library home and runs the same checks
  as `tapedeck doctor` (`src/cli/doctor.py`), naming the exact command to
  close any gap (e.g. `uv tool install mlx-whisper`, `brew install
  ffmpeg`). It installs nothing without consent.

## Open decisions

### 1. Should the repo be made public?

Currently local-only, no remote. If/when the answer is yes:

```sh
gh repo create tapedeck --public --source=. --remote=origin --push
```

(use `--private` instead of `--public` to keep it private but hosted, e.g.
to unblock CI runs on GitHub before a public launch).

### 2. What PyPI project name? — DECIDED 2026-08-18

`tapedeck-cli` (pyproject renamed, SPEC-cli-006 amended; the executable stays
`tapedeck`). To publish once credentials are in hand:

```sh
uv build
uv publish   # needs a PyPI token (UV_PUBLISH_TOKEN or ~/.pypirc)
```

Original notes:


Checked on 2026-08-13:

| Name            | Status                                    |
|-----------------|--------------------------------------------|
| `tapedeck`      | **taken** — an unrelated "music player" project (v0.0.5) already owns it |
| `tapedeck-cli`  | **available** (PyPI returns 404)          |

`pyproject.toml` currently declares `name = "tapedeck"`, which cannot be
published as-is. Decision needed: rename the PyPI distribution to
`tapedeck-cli` (keeping the `tapedeck` console-script entry point — users
would still type `tapedeck ...`, only `pip install tapedeck-cli` differs),
or pick another free name. Re-check availability before publishing, since
names can be claimed between now and then:

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/<name>/json
# 404 = free, 200 = taken
```

Once a name is chosen and set in `pyproject.toml`:

```sh
uv build
uv publish   # prompts for a PyPI API token, or set UV_PUBLISH_TOKEN
```

### 3. Homebrew tap later?

Not required for a first release (`uv tool install tapedeck-cli` covers
the documented install path in MANUAL.md). If wanted later, once the repo
is public and a release is tagged:

```sh
gh repo create <you>/homebrew-tapedeck --public
# then add a Formula/tapedeck.rb built from the PyPI sdist/wheel URL + sha256
```

No commands in this file have been run against any remote service other
than the read-only PyPI availability checks above.
