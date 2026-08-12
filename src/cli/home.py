"""$TAPEDECK_HOME: where the library is, and what a first run puts there.

Resolved on every run (SPEC-cli-001) and created when absent, so tapedeck on a
machine that has never run it lands in a working library instead of an error.

config.toml is the one file cli writes (library-layout write authority). It is
written exactly once, carrying the tool seams of SPEC-core-004 with their
defaults filled in and commented — visible, editable, and the reason a fresh
install can fetch and transcribe at all, since no component hardcodes a tool.
After that first write the file is the user's; we never rewrite it, so an edited
seam survives every later run.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import Failure

DEFAULT_HOME = "~/dev/storage/tapedeck"
CONFIG_NAME = "config.toml"
# archive/ and library/ belong to other components, but a home without them is
# not a library yet; tapedeck.db is index's to create when there is something in it.
DIRECTORIES = ("library", "archive")

CONFIG = """\
# tapedeck configuration — written on first run, yours to edit from here on.
#
# Every external tool sits behind a command template (SPEC-core-004): change the
# command and tapedeck uses the new tool, with no code change anywhere. Each one
# is a shell command, given its inputs in the environment.

[ingest]
# $TAPEDECK_VIDEO_ID, $TAPEDECK_VIDEO_URL, $TAPEDECK_DEST (an existing directory)
# in; a video.<ext> plus a yt-dlp-shaped info.json left in $TAPEDECK_DEST out.
fetcher_command = 'yt-dlp --no-playlist --write-info-json -f "bv*+ba/b" -o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'

[transcribe]
# $TAPEDECK_MEDIA, $TAPEDECK_VIDEO_ID, $TAPEDECK_OUT in; whisper-shaped JSON
# ({"segments": [{"start", "end", "text"}, ...]}) written to $TAPEDECK_OUT out.
transcriber_command = 'mlx_whisper --model mlx-community/whisper-large-v3-mlx --output-format json --output-dir "$(dirname "$TAPEDECK_OUT")" "$TAPEDECK_MEDIA"'
# Recorded in every transcript.json — supersession is judged on this label, so a
# different transcriber deserves a different name here.
model = "mlx-whisper/large-v3"

[ask]
# The assembled prompt on stdin, answer prose on stdout. tapedeck builds the
# Sources section itself from what retrieval returned; the answerer only cites.
answerer_command = 'claude -p'
"""


def resolve() -> Path:
    """The library home for this run — absolute, so every child process we hand
    it to resolves the same directory regardless of where it was started."""
    raw = os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME
    return Path(os.path.abspath(os.path.expanduser(raw)))


def prepare(home: Path) -> Path:
    """Make the home usable, then leave it alone."""
    try:
        for name in DIRECTORIES:
            (home / name).mkdir(parents=True, exist_ok=True)
        # Exclusive create: never clobber a config, not even when two runs race
        # for a fresh home — one writes the defaults, the other finds them there.
        with open(home / CONFIG_NAME, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(CONFIG)
    except FileExistsError:
        pass
    except OSError as exc:
        raise Failure(f"could not prepare {home} — {exc}") from exc
    return home
