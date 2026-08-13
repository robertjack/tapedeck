"""$TAPEDECK_HOME resolution and first-run scaffolding (SPEC-cli-001).

`config.toml` is the one file the cli owns (library-layout.md). It is written
once, on first run, with every external tool tapedeck will ever run already
filled in and explained — so a fresh install works out of the box and the seams
of SPEC-core-004 are visible in one editable file rather than buried in code.
After that the file is the user's: nothing here ever rewrites it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_HOME = "~/dev/storage/tapedeck"
CONFIG_NAME = "config.toml"
DIRS = ("library", "archive")

# Each default is the shape the component that runs it documents: ingest gives the
# fetcher $TAPEDECK_DEST and $TAPEDECK_VIDEO_URL, transcribe gives the transcriber
# $TAPEDECK_MEDIA and $TAPEDECK_OUT, ask pipes the prompt to the answerer on stdin.
# Single-quoted TOML throughout — these are shell lines and keep their own quoting.
CONFIG_TEMPLATE = """\
# tapedeck configuration — written on first run, yours to edit from now on.
#
# Every external tool tapedeck uses is a command template here (SPEC-core-004):
# change a line and tapedeck runs a different tool. Values below are the defaults.

[ingest]
# Downloads one video. Environment: $TAPEDECK_VIDEO_URL, $TAPEDECK_VIDEO_ID,
# $TAPEDECK_DEST (an existing staging dir). Must leave video.<ext> and a
# yt-dlp-shaped info.json in $TAPEDECK_DEST.
fetcher_command = 'yt-dlp --no-playlist --write-info-json -f "bv*+ba/b" -o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'

[transcribe]
# Transcribes one media file. Environment: $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID,
# $TAPEDECK_OUT. Must write whisper-shaped JSON ({"segments": [...]}) to $TAPEDECK_OUT.
transcriber_command = 'mlx_whisper --model mlx-community/whisper-large-v3-mlx --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
# Recorded in every transcript, so a better model can supersede older ones later.
model = "mlx-whisper/large-v3"

[ask]
# Answers one question: the assembled prompt arrives on stdin, prose goes to
# stdout. Citations are assembled by tapedeck from retrieval, never by this command.
answerer_command = "claude -p"
"""


def resolve() -> Path:
    """The library this run works on — read fresh every time, never cached."""
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def scaffold(home: Path) -> Path:
    """Make `home` a home. Idempotent: whatever is already there is left alone."""
    for name in DIRS:
        (home / name).mkdir(parents=True, exist_ok=True)
    config = home / CONFIG_NAME
    try:
        # Exclusive create: an existing config is never truncated, not even by two
        # tapedecks starting at once on a brand new home.
        with open(config, "x", encoding="utf-8") as fh:
            fh.write(CONFIG_TEMPLATE)
    except FileExistsError:
        return home
    print(f"created {config} — tapedeck's tool commands live there", file=sys.stderr)
    return home
