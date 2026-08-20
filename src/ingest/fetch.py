"""The external tools ingest reaches for, and the rules about what they leave.

Both tools sit behind command templates in `config.toml` (SPEC-core-004): the
fetcher downloads one video into a destination directory, the lister enumerates a
collection. Neither is ever named in code — swapping yt-dlp for something else is
one edited line in the user's config, and the durable evaluations use that same
seam to inject fakes.

The shipped defaults live here because the shape of a seam belongs to the
component that invokes it. The fetcher default carries two solved incidents
verbatim so a fresh install never re-suffers them: LESSON-0001's avc1 preference
(YouTube 403s AV1 in this setup) and LESSON-0006's client chain — some public
videos are now DRM-flagged to yt-dlp's default player clients, and the embedded
player (`web_embedded`) still gets clean streams, so it leads the chain with
`web_safari` excluded (its formats 403 intermittently without a PO-token
provider).

Also here: what counts as a downloaded video (SPEC-ingest-001) — a rule local
adds (SPEC-ingest-005) share unchanged, since a symlink that resolves is a file
like any other — what counts as one of our own staging directories
(SPEC-ingest-003), and how the fetcher's own chatter is handled (SPEC-ingest-004).
By default it is captured, not streamed: discarded on a clean exit, replayed in
full — the tool's own words — the moment the exit is not clean, because that is
the only diagnosis a DRM 403 ever gave us. While it runs, progress comes from the
staging directory's bytes rather than from parsing the tool, refreshed every
three seconds or so, so it is unchanged behind whatever the seam points at. When
the staged info json already names an expected size, the heartbeat turns that
into a percentage — capped at 99 and never decreasing, because merging streams
can transiently overshoot the estimate and only a clean exit ever means done.
When our stderr is a terminal, those reports stop stacking as scrollback and
redraw one line in place instead — a bar, not a log — ending with a real newline
the moment the fetch is over so whatever prints next starts its own line.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import tomllib
from pathlib import Path

from .sources import VIDEO_ID

CONFIG_NAME = "config.toml"
SECTION = "ingest"
FETCHER_KEY = "fetcher_command"
LISTER_KEY = "lister_command"
VIDEO_STEM = "video"
INFO_SUFFIX = "info.json"
# The siblings a fetcher writes into the same directory: fragments of a download
# in flight, and the sidecars it keeps beside the finished one.
NOT_VIDEO = (".json", ".part", ".ytdl", ".temp", ".tmp", ".description", ".webp", ".jpg", ".png")
STDERR_FD = 2  # --verbose's streaming target: a fetcher's chatter is progress, not our stdout
HEARTBEAT_S = 2.5  # cadence for the staging-bytes progress line: every three seconds or so
MAX_PERCENT = 99  # the estimate is approximate; only a clean exit ever says done
BAR_WIDTH = 20  # the redrawn TTY bar's width in characters

# The staging directory's name grammar (SPEC-ingest-003, library-layout.md): a
# fetch in progress or abandoned, never a stranger. Pinned here because three
# components have to agree on it and none of them see each other's source.
STAGING_PREFIX = ".fetching-"

DEFAULT_FETCHER_COMMAND = (
    "yt-dlp --no-playlist --write-info-json "
    '--extractor-args "youtube:player_client=web_embedded,default,-web_safari" '
    '-f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" '
    '-o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'
)
DEFAULT_LISTER_COMMAND = 'yt-dlp --flat-playlist --print "%(id)s" "$TAPEDECK_COLLECTION_URL"'


class ConfigError(ValueError):
    """The seam is not configured — a usage error the user fixes in config.toml."""


class FetchError(RuntimeError):
    """The tool ran and did not deliver. The library is untouched."""


def _seam(home: Path, key: str, label: str, default: str) -> str:
    path = home / CONFIG_NAME
    try:
        with open(path, "rb") as handle:
            config = tomllib.load(handle)
    except OSError:
        config = {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    command = (config.get(SECTION) or {}).get(key)
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(
            f"no {label} configured: add [{SECTION}].{key} to {path} — the shipped "
            f"default is: {default}"
        )
    return command


def fetcher(home: Path) -> str:
    return _seam(home, FETCHER_KEY, "fetcher command", DEFAULT_FETCHER_COMMAND)


def lister(home: Path) -> str:
    return _seam(home, LISTER_KEY, "lister command", DEFAULT_LISTER_COMMAND)


def _seam_env(home: Path, **extra: str) -> dict:
    return {**os.environ, "TAPEDECK_HOME": str(home), **extra}


def stage(library: Path, video_id: str) -> Path:
    """Somewhere to download into, inside the library's own filesystem.

    A staging area anywhere else turns installing the result into a copy across
    devices, and a copy can stop halfway — leaving a truncated video that every
    later run believes. Here the install is a rename. The dot prefix keeps the
    directory out of the library's readers while the download runs, in the shape
    `staging()` below can recognize from the name alone.
    """
    library.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{STAGING_PREFIX}{video_id}-", dir=library))


def staging(name: str) -> str | None:
    """Given a bare entry name from `library/`, the video id a staging directory
    of ours is fetching — or None if `name` is not one of ours (SPEC-ingest-003).

    Answers from the name alone, no filesystem access: a caller can ask about a
    directory entry it is only iterating, not one it has decided to open. The
    random suffix `tempfile.mkdtemp` appends is always dash-free, so splitting on
    the last '-' recovers the video id cleanly even though ids may themselves
    contain dashes.
    """
    if not name.startswith(STAGING_PREFIX):
        return None
    candidate, sep, suffix = name[len(STAGING_PREFIX) :].rpartition("-")
    if not sep or not suffix:
        return None
    return candidate if VIDEO_ID.fullmatch(candidate) else None


def _dir_size(path: Path) -> int:
    """Bytes landed in a staging directory so far — the tool-agnostic progress
    signal SPEC-ingest-004 asks for, read off the filesystem rather than parsed
    from anything a fetcher prints."""
    try:
        entries = list(path.iterdir())
    except OSError:
        return 0
    total = 0
    for entry in entries:
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            pass
    return total


def _load_info(dest: Path) -> dict | None:
    """The fetcher's metadata sidecar, if one is already on disk and readable —
    None otherwise, never raised. Used both by the heartbeat, which asks mid-fetch
    when the file may not exist yet or may still be mid-write, and by `read_info`
    below, which asks once the tool has exited and treats a miss as a failure."""
    if not dest.is_dir():
        return None
    candidates = sorted(dest.glob("*.json"))
    candidates.sort(key=lambda path: not path.name.endswith(INFO_SUFFIX))
    for path in candidates:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict):
            return document
    return None


def _size_field(source: dict) -> float | None:
    for key in ("filesize", "filesize_approx"):
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _declared_bytes(info: dict) -> float | None:
    """The expected total the staged info json names, when it names one at all
    (SPEC-ingest-004): the requested formats' sizes summed, or the top-level
    approximation when that is all the fetcher wrote. A bonus read from files
    already on disk — never a requirement, never a parse of the tool's stream."""
    formats = info.get("requested_formats")
    if isinstance(formats, list) and formats:
        sizes = [_size_field(fmt) for fmt in formats if isinstance(fmt, dict)]
        found = [size for size in sizes if size is not None]
        if found:
            return sum(found)
    return _size_field(info)


def _human(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _bar(percent: int) -> str:
    """A fill bar for the TTY redraw — monotonic with `percent`, never the tool's
    words, just a picture of the same number the piped line already carries."""
    filled = round(BAR_WIDTH * max(0, min(100, percent)) / 100)
    return "#" * filled + "-" * (BAR_WIDTH - filled)


def _report(video_id: str, current: float, declared: float | None, percent: int) -> str:
    if declared:
        return (
            f"ingest: fetching {video_id} — [{_bar(percent)}] {_human(current)} of "
            f"~{_human(declared)} ({percent}%)"
        )
    return f"ingest: fetching {video_id} — {_human(current)} so far"


def _watch(dest: Path, video_id: str, stop: threading.Event, tty: bool) -> None:
    """Reports staging bytes on our own stderr every few seconds, only while the
    fetcher is running — a handful of lines for a typical download, never a
    firehose, and unaffected by which tool sits behind the seam. When the staged
    info json already names an expected size, the line becomes a percentage
    against it; the percent only ever climbs, because the estimate is approximate
    and the actual bytes can transiently pass it while streams merge.

    Off a terminal each report is its own line (SPEC-ingest-004's original
    shape, and what every capture-based eval pins). On a terminal the same
    report redraws a single line in place instead of stacking as scrollback —
    presentation only, never a change to what a program reading the stream sees.
    """
    best_percent = 0
    while not stop.wait(HEARTBEAT_S):
        current = _dir_size(dest)
        info = _load_info(dest)
        declared = _declared_bytes(info) if info else None
        if declared and declared > 0:
            percent = min(MAX_PERCENT, max(0, round(current / declared * 100)))
            best_percent = max(best_percent, percent)
        else:
            best_percent = 0
        line = _report(video_id, current, declared, best_percent)
        if tty:
            sys.stderr.write(f"\r{line}\x1b[K")
            sys.stderr.flush()
        else:
            print(line, file=sys.stderr)


def run(
    command: str, home: Path, video_id: str, url: str, dest: Path, verbose: bool = False
) -> None:
    """Fetch one video into `dest`. Raises FetchError unless the tool exits clean.

    By default the tool's stdout and stderr are captured together and, on a clean
    exit, discarded — the pipeline's own heartbeat and closing line are the story
    of the fetch. On a failing exit the captured output is written to our stderr
    in full before the failure is raised, because the tool's own words are the
    diagnosis. `--verbose` (verbose=True) is the old raw passthrough: no capture,
    no heartbeat, the user asked to watch the tool itself.
    """
    env = _seam_env(
        home, TAPEDECK_VIDEO_ID=video_id, TAPEDECK_VIDEO_URL=url, TAPEDECK_DEST=str(dest)
    )
    if verbose:
        result = subprocess.run(command, shell=True, env=env, stdout=STDERR_FD)
        if result.returncode != 0:
            raise FetchError(f"the fetcher failed for {video_id} (exit {result.returncode})")
        return

    tty = sys.stderr.isatty()
    proc = subprocess.Popen(
        command,
        shell=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    stop = threading.Event()
    watcher = threading.Thread(target=_watch, args=(dest, video_id, stop, tty), daemon=True)
    watcher.start()
    output, _ = proc.communicate()
    stop.set()
    watcher.join()
    if tty:
        # end the redrawn line with a real newline: whatever prints next — the
        # failure replay, the closing account — starts fresh rather than tailing
        # onto the bar.
        sys.stderr.write("\n")
        sys.stderr.flush()
    if proc.returncode != 0:
        if output:
            sys.stderr.write(output if output.endswith("\n") else output + "\n")
        raise FetchError(f"the fetcher failed for {video_id} (exit {proc.returncode})")
    print(f"ingest: fetched {video_id} — {_human(_dir_size(dest))}", file=sys.stderr)


def collect(command: str, home: Path, url: str) -> str:
    """The lister's stdout for one collection URL, or FetchError if it failed. A
    half-read channel passed off as the whole one is worse than no listing."""
    env = _seam_env(home, TAPEDECK_COLLECTION_URL=url)
    result = subprocess.run(
        command, shell=True, env=env, stdout=subprocess.PIPE, text=True, errors="replace"
    )
    if result.returncode != 0:
        raise FetchError(f"the lister failed for {url} (exit {result.returncode})")
    return result.stdout or ""


def videos(directory: Path) -> list[Path]:
    """The downloaded video files in a directory — the published rule.

    `video.part` is a fetch in flight and `video.info.json` is a sidecar; neither
    is a video, so an entry holding only those has no video and is fetched again.
    A local add's symlink (SPEC-ingest-005) satisfies this the same way any other
    file does: `is_file()` follows it, and a dangling one reads as no video.
    """
    contents = sorted(directory.iterdir()) if directory.is_dir() else []
    return [
        path
        for path in contents
        if path.is_file()
        and path.stem == VIDEO_STEM
        and path.suffix
        and path.suffix.lower() not in NOT_VIDEO
    ]


def has_video(directory: Path) -> bool:
    """Whether this directory holds a real download (SPEC-core-003's skip test)."""
    return bool(videos(directory))


def find_video(dest: Path, video_id: str) -> Path:
    """The one video a fetch produced. Nothing usable is a failed fetch."""
    found = videos(dest)
    if not found:
        raise FetchError(f"the fetcher left no video file for {video_id}")
    return found[0]


def read_info(dest: Path, video_id: str) -> dict:
    """The fetcher's metadata sidecar, as it wrote it.

    yt-dlp names it after the output template (`video.info.json`); anything ending
    in `info.json` is the same promise, and a lone `.json` is taken as the sidecar
    too so a thinner fetcher still satisfies the seam.
    """
    document = _load_info(dest)
    if document is None:
        raise FetchError(
            f"the fetcher wrote no readable info json for {video_id} — there is no "
            "metadata to build meta.json from"
        )
    return document
