"""Durable evals: a forced re-fetch never costs you the video you already have
(SPEC-ingest-001).

Boundary: `python -m ingest add <url> --force`, library via $TAPEDECK_HOME,
fetcher via config.toml [ingest].fetcher_command (conftest.set_fetcher pins the
fetcher interface).

The dangerous shape is a staging directory on another filesystem: the move into
`library/<id>/` degrades into a copy, and a copy that stops halfway — full disk,
killed process, unplugged drive — can leave a truncated video beside a meta.json
that says the entry is complete, which every later run then believes. A boundary
eval cannot interrupt that copy, so the observable it holds instead is the one
that makes the copy impossible: the fetcher's destination is inside the library
home, so installing the result is a rename on one filesystem. The rest of the
clause is checked the way it can be — through the failures a fake fetcher can
actually produce.
"""

from pathlib import Path

from conftest import run_component, set_fetcher

VID = "dQw4w9WgXcQ"
OLD_BYTES = b"the download already in the library, worth keeping " * 32

RECORD_DEST = 'printf "%s\\n" "$TAPEDECK_DEST" >> "$TAPEDECK_HOME/dest-log"\n'
INFO = """cat > "$TAPEDECK_DEST/info.json" <<JSON
{"id": "$TAPEDECK_VIDEO_ID", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID"}
JSON
"""

FETCH_OLD = f"""#!/bin/sh
{RECORD_DEST}printf '%s' '{OLD_BYTES.decode()}' > "$TAPEDECK_DEST/video.mkv"
{INFO}"""

FETCH_NEW = f"""#!/bin/sh
{RECORD_DEST}printf 'the replacement download' > "$TAPEDECK_DEST/video.mp4"
{INFO}"""

# A fetcher that dies part way through writing the replacement: bytes on disk in
# the staging area, non-zero exit, nothing worth installing.
FETCH_DIES_MID_WRITE = f"""#!/bin/sh
{RECORD_DEST}printf 'half a replace' > "$TAPEDECK_DEST/video.mp4"
exit 1
"""

# A fetcher that produces a video but no metadata: the failure lands after the
# download, which is the last moment before the old entry would be disturbed.
FETCH_NO_INFO = f"""#!/bin/sh
{RECORD_DEST}printf 'the replacement download' > "$TAPEDECK_DEST/video.mp4"
"""


def add(home, *args):
    return run_component("ingest", ["add", *args], home)


def stocked(home):
    """One video in the library, fetched the ordinary way."""
    set_fetcher(home, FETCH_OLD)
    assert add(home, VID).returncode == 0
    entry = home / "library" / VID
    assert (entry / "video.mkv").read_bytes() == OLD_BYTES
    return entry


def destinations(home):
    return [Path(line) for line in (home / "dest-log").read_text().split()]


def test_the_fetch_is_staged_inside_the_library(home):
    stocked(home)
    dest = destinations(home)[0]
    library = (home / "library").resolve()
    assert dest.resolve().is_relative_to(home.resolve()), (
        f"the fetcher staged into {dest}, outside the library home — installing the "
        "result is then a cross-filesystem copy that can stop halfway"
    )
    assert any(part.startswith(".") for part in dest.resolve().relative_to(home.resolve()).parts), (
        f"staging {dest} is visible to readers of the library"
    )
    assert not dest.exists(), "a finished fetch leaves no staging directory behind"
    assert [p.name for p in library.iterdir()] == [VID], (
        "staging must not show up as an entry"
    )


def test_a_forced_refetch_that_dies_mid_write_keeps_the_old_video(home):
    entry = stocked(home)
    meta_before = (entry / "meta.json").read_text()

    set_fetcher(home, FETCH_DIES_MID_WRITE)
    assert add(home, VID, "--force").returncode == 1
    assert (entry / "video.mkv").read_bytes() == OLD_BYTES, (
        "a failed force-refetch must leave the old video byte-identical"
    )
    assert (entry / "meta.json").read_text() == meta_before
    assert not (entry / "video.mp4").exists(), "no half-written replacement in the entry"
    # And the entry is still usable: the next plain `add` sees a complete video
    # and skips the download rather than treating the entry as unfinished.
    set_fetcher(home, FETCH_NEW)
    assert add(home, VID).returncode == 0
    assert (entry / "video.mkv").read_bytes() == OLD_BYTES
    assert len(destinations(home)) == 2, "the surviving entry must skip the fetch"


def test_a_forced_refetch_with_unusable_metadata_keeps_the_old_video(home):
    entry = stocked(home)
    meta_before = (entry / "meta.json").read_text()

    set_fetcher(home, FETCH_NO_INFO)
    assert add(home, VID, "--force").returncode == 1
    assert (entry / "video.mkv").read_bytes() == OLD_BYTES
    assert (entry / "meta.json").read_text() == meta_before
    assert not (entry / "video.mp4").exists()


def test_a_successful_forced_refetch_replaces_the_video_exactly_once(home):
    entry = stocked(home)
    set_fetcher(home, FETCH_NEW)
    assert add(home, VID, "--force").returncode == 0
    assert (entry / "video.mp4").read_bytes() == b"the replacement download"
    assert not (entry / "video.mkv").exists(), "one entry never holds two videos"
    assert [p.name for p in (home / "library").iterdir()] == [VID]
