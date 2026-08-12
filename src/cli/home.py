"""$TAPEDECK_HOME resolution and the config.toml the cli owns.

The home is resolved on every run and created on first use (SPEC-cli-001), so
`tapedeck` works on a machine that has never seen it. config.toml is written
exactly once, with every tool seam (SPEC-core-004) spelled out and annotated:
the defaults are live values rather than commented-out suggestions, so a fresh
install can `add` immediately, and they are all in one visible place to edit.
After that first write the file is the user's — scaffolding never rewrites,
merges, or reformats it.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = "~/dev/storage/tapedeck"
CONFIG_NAME = "config.toml"
# Created eagerly so an empty library still has the shape the layout contract
# names; tapedeck.db is the index's to make when there is something to index.
DIRS = ("library", "archive")

CONFIG_TEMPLATE = """\
# tapedeck — created on first run, yours to edit from here on.
#
# Every external tool sits behind a command template (SPEC-core-004): tapedeck
# runs it through the shell, passes what it needs in environment variables, and
# reads back the file it writes. Any tool honouring the same seam can replace
# the default — nothing below is hardcoded anywhere else.

[ingest]
# Downloads one video. In: $TAPEDECK_VIDEO_URL, $TAPEDECK_VIDEO_ID, $TAPEDECK_DEST.
# Out: $TAPEDECK_DEST/video.<ext> plus a yt-dlp-shaped info.json beside it.
fetcher_command = 'yt-dlp --no-playlist --write-info-json -f "bv*+ba/b" -o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'

[transcribe]
# Transcribes one video. In: $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID, $TAPEDECK_OUT.
# Out: whisper-shaped JSON ({"segments": [{"start", "end", "text"}, ...]}) at $TAPEDECK_OUT.
transcriber_command = 'mlx_whisper --model mlx-community/whisper-large-v3-mlx --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
# Recorded in every transcript, so a better model can supersede old ones later.
model = "mlx-whisper/large-v3"

[ask]
# Answers one question. In: the assembled prompt on stdin. Out: the answer on stdout.
# tapedeck retrieves the sources and writes the citations; this only drafts prose.
answerer_command = "claude -p"
"""


def home_dir() -> Path:
    """Where the library lives — resolved fresh on every run, never cached."""
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def ensure(home: Path) -> Path:
    """Make the home usable: its directories exist, and config.toml is there."""
    for name in DIRS:
        (home / name).mkdir(parents=True, exist_ok=True)
    config = home / CONFIG_NAME
    if not config.exists():
        try:
            # Exclusive create: two tapedecks starting at once must not have one
            # overwrite a config the other has already written (or the user has).
            with open(config, "x", encoding="utf-8", newline="\n") as f:
                f.write(CONFIG_TEMPLATE)
        except FileExistsError:
            pass
    return home
