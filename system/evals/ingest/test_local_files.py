"""Durable evals: a video does not have to come from YouTube (SPEC-ingest-005).

Boundary: `python -m ingest add <path>`, library via $TAPEDECK_HOME. No fetcher
seam is configured anywhere in this suite — that is part of what is pinned: a
local add downloads nothing, so a machine with no fetcher can still do it.

The fixture media is real, made with ffmpeg, because the duration in meta.json
is read from the file itself and every citation this system verifies is checked
against that number. A fake byte string would prove nothing about the one field
here that other components trust.
"""

import json
import shutil
import subprocess

import pytest

from conftest import run_component

SECONDS = 3


def needs_ffmpeg():
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is genuinely absent here; local ingest reads real media")


def make_video(path, seconds=SECONDS, tone=440):
    """A real, tiny media file. `tone` varies the *contents* without varying the
    name or the duration, which is what makes the id evals falsifiable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={tone}:duration={seconds}",
         "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={seconds}",
         "-shortest", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
    return path


def add(home, *args):
    return run_component("ingest", ["add", *args], home)


def entry_of(home, video_id):
    return home / "library" / video_id


def sole_entry(home):
    """The one library entry, whatever id it was given — the id is a digest, so
    no eval may hard-code it without pinning the digest function itself."""
    entries = [p for p in (home / "library").iterdir() if not p.name.startswith(".")]
    assert len(entries) == 1, f"expected exactly one entry: {[p.name for p in entries]}"
    return entries[0]


def test_a_local_file_becomes_a_library_entry(home, tmp_path):
    needs_ffmpeg()
    source = make_video(tmp_path / "footage" / "Team Meeting.mp4")
    r = add(home, str(source))
    assert r.returncode == 0, r.stderr

    entry = sole_entry(home)
    assert len(entry.name) == 11, f"the id is the layout's 11 chars: {entry.name!r}"

    meta = json.loads((entry / "meta.json").read_text())
    assert meta["id"] == entry.name
    assert meta["title"] == "Team Meeting", "the title is the filename without extension"
    assert meta["channel"] == "", "a local file has no publisher to name"
    assert meta["url"] == source.resolve().as_uri(), (
        f"the url is the file's own address, which is what the deep-link rule "
        f"builds a moment from: {meta['url']!r}"
    )
    assert meta["duration_s"] == SECONDS, (
        f"the duration is read from the media, not guessed: {meta['duration_s']!r}"
    )

    videos = [p for p in entry.iterdir() if p.name.startswith("video.")]
    assert len(videos) == 1, f"the entry holds one video: {[p.name for p in videos]}"
    assert videos[0].is_symlink(), "the library references the file, it does not copy it"
    assert videos[0].resolve() == source.resolve()


def test_the_id_is_the_contents_so_a_rename_is_the_same_entry(home, tmp_path):
    """Renamed and moved, the same footage is the same entry and the second add
    is the ordinary skip — while different contents under the same name are a
    different video."""
    needs_ffmpeg()
    first = make_video(tmp_path / "a" / "clip.mp4")
    assert add(home, str(first)).returncode == 0
    original = sole_entry(home).name

    moved = tmp_path / "b" / "renamed-clip.mp4"
    moved.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(first), str(moved))
    assert add(home, str(moved)).returncode == 0
    assert sole_entry(home).name == original, "the same footage must not fork an entry"

    different = make_video(tmp_path / "c" / "clip.mp4", tone=880)
    assert add(home, str(different)).returncode == 0
    ids = {p.name for p in (home / "library").iterdir() if not p.name.startswith(".")}
    assert len(ids) == 2, f"different contents are a different video: {ids}"


def test_a_dangling_link_reads_as_an_entry_with_no_video(home, tmp_path):
    """The degradation SPEC-ingest-005 promises: delete the original and the
    knowledge stands while the media does not — the `rm --media-only` state the
    system already understands, reached by the user's own file manager."""
    needs_ffmpeg()
    source = make_video(tmp_path / "vanishing.mp4")
    assert add(home, str(source)).returncode == 0
    entry = sole_entry(home)
    assert (entry / "meta.json").is_file()

    source.unlink()
    video = next(p for p in entry.iterdir() if p.name.startswith("video."))
    assert not video.is_file(), (
        "a dangling link must read as no video, so the entry is media-only rather "
        "than broken"
    )
    assert (entry / "meta.json").is_file(), "the metadata is the library's, not the file's"


def test_a_path_that_is_not_there_is_a_usage_error(home, tmp_path):
    r = add(home, str(tmp_path / "no-such-file.mp4"))
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert not (home / "library").exists() or not list((home / "library").iterdir())


def test_a_file_with_no_readable_duration_fails_without_an_entry(home, tmp_path):
    """A guessed duration would launder itself into evidence — every citation
    this system verifies is checked against it — so the add fails instead."""
    needs_ffmpeg()
    junk = tmp_path / "not-really-video.mp4"
    junk.write_text("this is not media")
    r = add(home, str(junk))
    assert r.returncode == 1, f"{r.stdout}\n{r.stderr}"
    entries = [] if not (home / "library").exists() else [
        p for p in (home / "library").iterdir() if not p.name.startswith(".")
    ]
    assert entries == [], f"a failed local add leaves no partial entry: {entries}"
