# tapedeck

**Your local video brain.** Point it at a YouTube video and it downloads it,
transcribes it on your own machine, archives it as readable markdown, and makes
every spoken moment searchable — then answers your questions with citations that
deep-link to the exact second someone said the thing.

```
tapedeck add "https://www.youtube.com/watch?v=..."
tapedeck search "verification bottleneck"
tapedeck ask "what did anyone say about pricing agent work?"
```

Nothing leaves your machine except the download itself. Your videos, transcripts,
and index live in a plain folder you own; delete the tool and your library is
still there, still readable.

## What you get

- **`add`** — the whole pipeline in one command: download (with a progress bar),
  local transcription, a markdown archive page where every paragraph is one click
  from its moment in the video, and full-text indexing. Your terminal is back in
  a couple of minutes.
- **`search`** — ranked full-text search over everything ever said, each result
  carrying a timestamp and a deep link that opens YouTube right at that moment.
- **`ask`** — questions answered from your library, with every citation
  mechanically verified against the videos before you see it. If it can't back an
  answer, it says "not in the library" instead of guessing.
- **The wiki** — an optional layer where an AI maintainer files each video into
  an interlinked knowledge base: one page per video, notes for ideas that recur
  across videos, every link verified. It reads beautifully in
  [Obsidian](https://obsidian.md) and compounds as your library grows. Filings
  run in the background and are billed to your own `claude` account — a few
  dollars per video, off by default until you configure it.

## Install (macOS, Apple Silicon)

```sh
brew install uv          # if you don't have uv yet
uv tool install tapedeck-cli
tapedeck setup
```

`setup` checks your machine and prints the exact command for anything missing —
nothing installs without your say-so (`tapedeck setup --yes` runs the printed
commands for you). When YouTube inevitably changes something,
`tapedeck setup --refresh` updates your tools the same way.

On an Intel Mac, point the transcriber at a non-MLX tool via `config.toml` —
`tapedeck help manual` covers it.

## Quickstart

```sh
tapedeck add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
tapedeck list                      # what's in your library
tapedeck search "never gonna"      # find the moment
tapedeck ask "what is this video actually about?"
tapedeck help manual               # the full manual, in your pager
```

Everything is a plain file: videos and transcripts under your library home
(default `~/Tapedeck`), archive pages as markdown, the index as one SQLite
database. Every derived file can be rebuilt from the one before it.

## Staying healthy

- `tapedeck doctor` — read-only diagnosis of your setup
- `tapedeck setup --refresh` — update the underlying tools (yt-dlp et al.)
- `tapedeck help manual` — the complete manual, including a troubleshooting
  reference for the failures YouTube likes to invent

## Development

The test suite runs with `just eval-all` (pytest over `system/evals/`), and CI
runs it on macOS for every push. External tools are faked through config seams,
so the suite needs no network and installs nothing.

## License

MIT — see [LICENSE](LICENSE).
