"""Ephemeral unit tests for ingest — the durable evals in system/evals/ingest/
are the acceptance criteria; these cover the seams and edges from the inside."""

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest import __main__ as cli  # noqa: E402
from ingest import fetch, local, meta, sources  # noqa: E402

VID = "dQw4w9WgXcQ"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    (h / "config.toml").write_text("# fixture\n")
    return h


def set_seams(home, fetcher=None, lister=None):
    lines = ["[ingest]"]
    if fetcher is not None:
        script = home / "fetch.sh"
        script.write_text(fetcher)
        lines.append(f'fetcher_command = "sh {script}"')
    if lister is not None:
        script = home / "list.sh"
        script.write_text(lister)
        lines.append(f'lister_command = "sh {script}"')
    (home / "config.toml").write_text("\n".join(lines) + "\n")


def run(home, *argv):
    os.environ["TAPEDECK_HOME"] = str(home)
    return cli.main(list(argv))


# --- the id grammar ------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        VID,
        f"  {VID}  ",
        f"https://www.youtube.com/watch?v={VID}",
        f"http://youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?t=42",
        f"youtu.be/{VID}",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/watch?v={VID}&list=PLsomething",
        f"https://www.youtube.com/watch?list=PLsomething&v={VID}",
    ],
)
def test_single_video_forms(target):
    assert sources.resolve(target) == (sources.VIDEO, VID)
    assert sources.video_id(target) == VID


@pytest.mark.parametrize(
    "target",
    [
        "https://www.youtube.com/playlist?list=PLtestfixture01",
        "https://www.youtube.com/@handle",
        "https://www.youtube.com/@handle/videos",
        "https://www.youtube.com/@handle/streams",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos",
        "https://www.youtube.com/c/Name",
        "https://www.youtube.com/user/name",
        "youtube.com/@handle",
    ],
)
def test_collection_forms(target):
    kind, value = sources.resolve(target)
    assert kind == sources.COLLECTION
    assert value == target


@pytest.mark.parametrize(
    "target",
    [
        "",
        "   ",
        "not-an-id",
        "https://example.com/watch?v=" + VID,
        "https://vimeo.com/12345",
        f"file:///tmp/{VID}",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=too-short",
        "https://www.youtube.com/shorts/",
        "https://www.youtube.com/playlist",
        "https://www.youtube.com/channel",
        "https://www.youtube.com/@",
        "https://www.youtube.com/@handle/community",
        f"https://youtu.be/{VID}/extra",
    ],
)
def test_rejected_targets(target):
    with pytest.raises(sources.BadRequest):
        sources.resolve(target)


def test_video_id_refuses_a_collection():
    with pytest.raises(sources.BadRequest):
        sources.video_id("https://www.youtube.com/@handle")


def test_video_ids_filters_dedupes_and_keeps_order():
    listing = f"\n{VID}\nplainvide00\n{VID}\nnot-an-id\n  another11ch  \n[download] noise\n"
    assert sources.video_ids(listing) == [VID, "plainvide00", "another11ch"]
    assert sources.video_ids("") == []


def test_canonical_url():
    assert sources.canonical_url(VID) == f"https://www.youtube.com/watch?v={VID}"


# --- what counts as a downloaded video -----------------------------------


def test_videos_sees_containers_only(tmp_path):
    for name in (
        "video.mp4",
        "video.part",
        "video.mkv.part",
        "video.ytdl",
        "video.temp",
        "video.tmp",
        "video.info.json",
        "video.json",
        "video.description",
        "video.webp",
        "video.jpg",
        "video.png",
        "video",
        "other.mkv",
    ):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in fetch.videos(tmp_path)] == ["video.mp4"]
    assert fetch.has_video(tmp_path)


def test_an_entry_with_only_a_part_file_has_no_video(tmp_path):
    (tmp_path / "video.part").write_bytes(b"half")
    assert fetch.videos(tmp_path) == []
    assert not fetch.has_video(tmp_path)
    assert not fetch.has_video(tmp_path / "nope")


def test_staging_is_dotted_and_inside_the_library(tmp_path):
    dest = fetch.stage(tmp_path / "library", VID)
    assert dest.parent == tmp_path / "library"
    assert dest.name.startswith(".")
    assert VID in dest.name


# --- the staging-directory predicate (SPEC-ingest-003) --------------------


def test_staging_recognizes_a_real_directory_it_made(tmp_path):
    dest = fetch.stage(tmp_path / "library", VID)
    assert fetch.staging(dest.name) == VID


def test_staging_recognizes_the_name_alone_no_filesystem_touched():
    # no directory created at all — the answer comes from the string
    assert fetch.staging(f".fetching-{VID}-ab12cd34") == VID


def test_staging_handles_a_video_id_that_itself_contains_a_dash():
    dashed = "abc-defghij"
    assert sources.VIDEO_ID.fullmatch(dashed)
    assert fetch.staging(f".fetching-{dashed}-ab12cd34") == dashed


@pytest.mark.parametrize(
    "name",
    [
        "dQw4w9WgXcQ",  # a video id itself, not a staging directory
        ".fetching-",
        ".fetching-tooshort-ab12cd34",
        ".fetching-not_eleven_chars_long-ab12cd34",
        "not-ours-at-all",
        "",
        ".hidden-but-not-ours",
    ],
)
def test_staging_says_none_for_anything_not_ours(name):
    assert fetch.staging(name) is None


def test_staging_is_exported_from_the_package_alongside_video_id_and_has_video():
    import ingest

    assert ingest.staging is fetch.staging
    assert ingest.VIDEO_ID is sources.VIDEO_ID
    assert ingest.has_video is fetch.has_video


# --- the config seams ----------------------------------------------------


def test_missing_config_names_the_key_and_the_default(tmp_path):
    with pytest.raises(fetch.ConfigError) as caught:
        fetch.fetcher(tmp_path)
    assert "fetcher_command" in str(caught.value)
    assert "yt-dlp" in str(caught.value)


def test_broken_toml_is_a_config_error(tmp_path):
    (tmp_path / "config.toml").write_text("[ingest\n")
    with pytest.raises(fetch.ConfigError):
        fetch.lister(tmp_path)


def test_blank_seam_is_a_config_error(tmp_path):
    (tmp_path / "config.toml").write_text('[ingest]\nfetcher_command = "  "\n')
    with pytest.raises(fetch.ConfigError):
        fetch.fetcher(tmp_path)


def test_shipped_fetcher_default_carries_lesson_0001_and_lesson_0006():
    assert fetch.DEFAULT_FETCHER_COMMAND == (
        'yt-dlp --no-playlist --write-info-json --extractor-args '
        '"youtube:player_client=web_embedded,default,-web_safari" '
        '-f "bv*[vcodec^=avc1][height<=1080]+ba/bv*[height<=1080]+ba/b" '
        '-o "$TAPEDECK_DEST/video.%(ext)s" "$TAPEDECK_VIDEO_URL"'
    )
    assert fetch.DEFAULT_LISTER_COMMAND == (
        'yt-dlp --flat-playlist --print "%(id)s" "$TAPEDECK_COLLECTION_URL"'
    )


def test_read_info_prefers_the_info_sidecar(tmp_path):
    (tmp_path / "aaa.json").write_text('{"title": "wrong"}')
    (tmp_path / "video.info.json").write_text('{"title": "right"}')
    assert fetch.read_info(tmp_path, VID)["title"] == "right"


def test_read_info_skips_unreadable_json(tmp_path):
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "list.json").write_text("[1, 2]")
    with pytest.raises(fetch.FetchError):
        fetch.read_info(tmp_path, VID)


def test_read_info_is_none_before_any_json_lands(tmp_path):
    assert fetch._load_info(tmp_path) is None
    assert fetch._load_info(tmp_path / "nope") is None


# --- normalization -------------------------------------------------------


def test_normalize_fills_the_schema_shape():
    document = meta.normalize(
        VID,
        sources.canonical_url(VID),
        {
            "title": "  Building\nThings  ",
            "uploader": "Fixture Channel",
            "upload_date": "20260115",
            "duration": 719.6,
            "webpage_url": "https://www.youtube.com/watch?v=" + VID,
            "description": "A fixture.",
            "chapters": [{"title": "Intro", "start_time": 0}],
            "unknown_key": "dropped",
        },
    )
    assert document["title"] == "Building Things"
    assert document["channel"] == "Fixture Channel"
    assert document["upload_date"] == "2026-01-15"
    assert document["duration_s"] == 720
    assert document["chapters"] == [{"title": "Intro", "start_s": 0}]
    assert "unknown_key" not in document
    assert set(document) <= {
        "id", "title", "channel", "upload_date", "duration_s", "url",
        "description", "chapters", "ingested_at",
    }


def test_normalize_defaults_what_the_fetcher_omitted():
    document = meta.normalize(VID, "fallback-url", {"title": "T"})
    assert document["channel"] == ""
    assert document["duration_s"] == 0
    assert document["url"] == "fallback-url"
    assert len(document["upload_date"]) == 10
    assert "description" not in document and "chapters" not in document


def test_normalize_reads_an_iso_timestamp_as_its_date():
    assert meta.normalize(VID, "u", {"title": "T", "upload_date": "2026-02-02T10:00:00Z"})[
        "upload_date"
    ] == "2026-02-02"


def test_normalize_needs_a_title():
    for info in ({}, {"title": "   "}, [], None):
        with pytest.raises(meta.BadMeta):
            meta.normalize(VID, "u", info)


def test_chapters_drop_the_unusable():
    assert meta.chapters(
        [
            {"title": "ok", "start_time": 12.5},
            {"title": "no start"},
            {"title": "negative", "start_time": -1},
            "not a chapter",
        ]
    ) == [{"title": "ok", "start_s": 12.5}]
    assert meta.chapters(None) == []


def test_meta_write_leaves_no_temporary(tmp_path):
    meta.write(tmp_path, {"id": VID, "title": "T"})
    assert json.loads((tmp_path / "meta.json").read_text())["id"] == VID
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]


# --- the verbs, end to end in-process ------------------------------------

FETCH_OK = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/fetch-count"
printf 'bytes' > "$TAPEDECK_DEST/video.mp4"
printf '{"title": "T", "uploader": "C", "upload_date": "20260115", "duration": 10}' \
  > "$TAPEDECK_DEST/video.info.json"
"""


def test_add_then_skip_then_force(home, capsys):
    set_seams(home, fetcher=FETCH_OK)
    assert run(home, "add", VID) == 0
    assert Path(capsys.readouterr().out.strip()).name == VID
    assert run(home, "add", f"https://youtu.be/{VID}") == 0
    assert (home / "fetch-count").read_text().count("run") == 1
    assert run(home, "add", VID, "--force") == 0
    assert (home / "fetch-count").read_text().count("run") == 2
    assert [p.name for p in (home / "library").iterdir()] == [VID]


def test_a_partial_download_is_re_fetched(home):
    set_seams(home, fetcher=FETCH_OK)
    assert run(home, "add", VID) == 0
    entry = home / "library" / VID
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half")
    assert run(home, "add", VID) == 0
    assert (home / "fetch-count").read_text().count("run") == 2
    assert (entry / "video.mp4").is_file()


def test_a_failing_fetcher_leaves_nothing(home, capsys):
    set_seams(home, fetcher='#!/bin/sh\nprintf x > "$TAPEDECK_DEST/video.mp4"\nexit 3\n')
    assert run(home, "add", VID) == 1
    assert "error" in capsys.readouterr().err
    assert list((home / "library").iterdir()) == []


def test_expand_single_never_runs_the_lister(home, capsys):
    set_seams(home, lister='#!/bin/sh\necho ran >> "$TAPEDECK_HOME/list-count"\n')
    assert run(home, "expand", f"https://www.youtube.com/shorts/{VID}") == 0
    assert capsys.readouterr().out.split() == [VID]
    assert not (home / "list-count").exists()


def test_expand_collection_and_its_failure(home, capsys):
    set_seams(home, lister=f'#!/bin/sh\nprintf "%s\\n" {VID} bad {VID}\n')
    assert run(home, "expand", "https://www.youtube.com/@handle") == 0
    assert capsys.readouterr().out.split() == [VID]
    set_seams(home, lister="#!/bin/sh\nexit 2\n")
    assert run(home, "expand", "https://www.youtube.com/@handle") == 1
    assert capsys.readouterr().out == ""


def test_add_refuses_a_collection_before_reading_config(home, capsys):
    assert run(home, "add", "https://www.youtube.com/@handle") == 2
    assert "collection" in capsys.readouterr().err


def test_missing_fetcher_config_is_a_usage_error(home, capsys):
    assert run(home, "add", VID) == 2
    assert "fetcher" in capsys.readouterr().err


# --- SPEC-ingest-004: captured, not streamed ------------------------------

NOISE = "NOISE-MARKER"
CHATTY_OK = f"""#!/bin/sh
echo "{NOISE} extracting" >&2
printf 'bytes' > "$TAPEDECK_DEST/video.mp4"
printf '{{"title": "T", "uploader": "C", "upload_date": "20260115", "duration": 10}}' \
  > "$TAPEDECK_DEST/video.info.json"
"""
CHATTY_FAILS = f"""#!/bin/sh
echo "{NOISE} boom" >&2
exit 1
"""


def test_a_clean_fetch_swallows_the_chatter(home, capsys):
    set_seams(home, fetcher=CHATTY_OK)
    assert run(home, "add", VID) == 0
    captured = capsys.readouterr()
    assert NOISE not in captured.err
    assert NOISE not in captured.out


def test_verbose_streams_the_fetcher_raw(home, capsys):
    set_seams(home, fetcher=CHATTY_OK)
    assert run(home, "add", VID, "--verbose") == 0
    assert NOISE in capsys.readouterr().err


def test_a_failing_fetch_replays_its_output_before_the_failure_line(home, capsys):
    set_seams(home, fetcher=CHATTY_FAILS)
    assert run(home, "add", VID) == 1
    err = capsys.readouterr().err
    assert NOISE in err
    assert err.index(NOISE) < err.index("error:")
    assert "fetcher" in err.lower()


def test_progress_is_read_from_staging_bytes_not_the_tool(tmp_path):
    dest = tmp_path
    (dest / "video.mp4").write_bytes(b"x" * 2048)
    assert fetch._dir_size(dest) == 2048
    assert re.search(r"\d+(\.\d+)?\s*(B|KB|MB)", fetch._human(fetch._dir_size(dest)))


# --- SPEC-ingest-004 (amended): a declared size becomes a capped percentage --


def test_declared_bytes_sums_requested_formats():
    info = {"requested_formats": [{"filesize": 300000}, {"filesize_approx": 100000}]}
    assert fetch._declared_bytes(info) == 400000


def test_declared_bytes_falls_back_to_the_top_level_approximation():
    assert fetch._declared_bytes({"filesize_approx": 999}) == 999
    assert fetch._declared_bytes({"filesize": 111}) == 111


def test_declared_bytes_is_none_with_no_size_anywhere():
    assert fetch._declared_bytes({"title": "T"}) is None
    assert fetch._declared_bytes({"requested_formats": [{"format_id": "137"}]}) is None


def test_heartbeat_cadence_is_roughly_three_seconds():
    assert 2 <= fetch.HEARTBEAT_S <= 3.5


def test_max_percent_never_exceeds_the_cap():
    assert fetch.MAX_PERCENT == 99


# --- SPEC-ingest-004 (amended): a TTY redraws one bar instead of stacking ---


def test_bar_fills_monotonically_with_percent():
    empty = fetch._bar(0)
    half = fetch._bar(50)
    full = fetch._bar(100)
    assert len(empty) == len(half) == len(full) == fetch.BAR_WIDTH
    assert empty.count("#") == 0
    assert full.count("#") == fetch.BAR_WIDTH
    assert 0 < half.count("#") < fetch.BAR_WIDTH


def test_report_carries_the_percent_when_a_size_is_declared():
    line = fetch._report(VID, 512, 1024, 50)
    assert "(50%)" in line
    assert VID in line
    assert "[" in line and "]" in line  # the bar itself


def test_report_degrades_to_plain_bytes_with_no_declared_size():
    line = fetch._report(VID, 512, None, 0)
    assert "%" not in line
    assert VID in line


def test_watch_off_a_tty_prints_one_full_line_per_report(tmp_path, capsys):
    import threading

    (tmp_path / "video.mp4").write_bytes(b"x" * 10)
    stop = threading.Event()
    stop.set()  # loop body never runs; exercised end-to-end by the durable evals
    fetch._watch(tmp_path, VID, stop, tty=False)
    assert capsys.readouterr().err == ""


def test_watch_writes_bare_carriage_returns_when_tty(tmp_path):
    import io
    import threading
    import time

    (tmp_path / "video.mp4").write_bytes(b"x" * 10)
    buf = io.StringIO()
    buf.isatty = lambda: True
    stop = threading.Event()

    def stop_soon():
        time.sleep(fetch.HEARTBEAT_S * 2.2)
        stop.set()

    real_stderr = fetch.sys.stderr
    fetch.sys.stderr = buf
    try:
        t = threading.Thread(target=stop_soon)
        t.start()
        fetch._watch(tmp_path, VID, stop, tty=True)
        t.join()
    finally:
        fetch.sys.stderr = real_stderr
    seen = buf.getvalue()
    assert seen.count("\r") >= 2
    assert "\n" not in seen  # no scrollback — every report overwrites in place


# --- SPEC-ingest-005: a video does not have to come from YouTube -----------


def test_local_target_finds_an_existing_file_and_resolves_it(tmp_path):
    real = tmp_path / "sub" / "clip.mp4"
    real.parent.mkdir()
    real.write_bytes(b"hello")
    link = tmp_path / "via-symlink.mp4"
    link.symlink_to(real)
    assert sources.local_target(str(link)) == real.resolve()
    assert sources.local_target(f"  {link}  ") == real.resolve()  # whitespace tolerated


def test_local_target_is_none_for_missing_files_and_directories(tmp_path):
    assert sources.local_target(str(tmp_path / "nope.mp4")) is None
    assert sources.local_target(str(tmp_path)) is None  # a directory is not a file
    assert sources.local_target("") is None
    assert sources.local_target("   ") is None


def test_local_id_is_a_content_digest_of_the_right_shape(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"same bytes")
    b.write_bytes(b"same bytes")
    different = tmp_path / "c.mp4"
    different.write_bytes(b"different bytes")

    id_a, id_b, id_c = sources.local_id(a), sources.local_id(b), sources.local_id(different)
    assert id_a == id_b, "identical contents must yield the same id regardless of name"
    assert id_a != id_c
    assert sources.VIDEO_ID.fullmatch(id_a), f"must be a well-formed video id: {id_a!r}"


def test_resolve_prefers_a_local_file_over_url_parsing(tmp_path):
    # an absolute path is never a URL — the file check must run first, or this
    # would otherwise fail as "not a YouTube URL"
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"local content")
    kind, value = sources.resolve(str(path))
    assert kind == sources.VIDEO
    assert value == sources.local_id(path.resolve())


def test_a_bare_filename_that_looks_like_a_video_id_still_resolves_as_local(
    tmp_path, monkeypatch
):
    # named exactly like a bare video id, and it exists in the cwd — the file on
    # disk must win over the id-shortcut, since resolve checks the filesystem
    # before it considers anything about YouTube's grammar at all
    monkeypatch.chdir(tmp_path)
    path = tmp_path / VID
    path.write_bytes(b"local content, not a real youtube id")
    kind, value = sources.resolve(VID)
    assert kind == sources.VIDEO
    assert value == sources.local_id(path.resolve())
    assert value != VID  # the digest, never the filename


def test_local_metadata_reflects_only_the_file_itself(tmp_path):
    source = (tmp_path / "My Recording.mkv").resolve()
    source.write_bytes(b"stand-in bytes")

    assert local.title(source) == "My Recording"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", local.upload_date(source))
    assert local.file_url(source) == source.as_uri()
    assert local.file_url(source).startswith("file:///")


def test_duration_s_wraps_ffprobe_failure_as_media_error(tmp_path, monkeypatch):
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "Invalid data found when processing input"

    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: FakeResult())
    with pytest.raises(local.MediaError):
        local.duration_s(tmp_path / "junk.mp4")


def test_duration_s_wraps_a_missing_binary_as_media_error(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("no ffprobe")

    monkeypatch.setattr(local.subprocess, "run", missing)
    with pytest.raises(local.MediaError):
        local.duration_s(tmp_path / "x.mp4")


def test_duration_s_rounds_a_clean_reading(tmp_path, monkeypatch):
    class FakeResult:
        returncode = 0
        stdout = "3.024000\n"
        stderr = ""

    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: FakeResult())
    assert local.duration_s(tmp_path / "x.mp4") == 3


def test_install_link_creates_a_symlink_named_like_a_fetch(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    source = (tmp_path / "footage.mov").resolve()
    source.write_bytes(b"bytes")
    link = local.install_link(dest, source)
    assert link.name == "video.mov"
    assert link.is_symlink()
    assert link.resolve() == source


def test_add_local_end_to_end_with_ffprobe_stubbed(home, monkeypatch, capsys):
    """add_local's whole path — id, symlink, meta.json — without depending on a
    real ffprobe binary; the durable evals cover the real-media case."""
    monkeypatch.setattr(local, "duration_s", lambda path: 42)
    source = (home.parent / "Lecture One.mp4").resolve()
    source.write_bytes(b"stand-in video bytes")

    assert run(home, "add", str(source)) == 0
    printed = capsys.readouterr().out.strip()
    video_id = Path(printed).name
    assert video_id == sources.local_id(source)

    entry = home / "library" / video_id
    document = json.loads((entry / "meta.json").read_text())
    assert document["title"] == "Lecture One"
    assert document["channel"] == ""
    assert document["duration_s"] == 42
    assert document["url"] == source.as_uri()

    video = next(p for p in entry.iterdir() if p.name.startswith("video."))
    assert video.is_symlink()
    assert video.resolve() == source

    # a second add of the identical bytes at a different name is the same entry
    renamed = (home.parent / "renamed.mp4").resolve()
    renamed.write_bytes(source.read_bytes())
    assert run(home, "add", str(renamed)) == 0
    assert [p.name for p in (home / "library").iterdir()] == [video_id]


def test_add_local_fails_cleanly_with_no_readable_duration(home, monkeypatch):
    def boom(path):
        raise local.MediaError("no duration here")

    monkeypatch.setattr(local, "duration_s", boom)
    source = (home.parent / "junk.mp4").resolve()
    source.write_bytes(b"not really media")

    assert run(home, "add", str(source)) == 1
    assert not (home / "library").exists() or list((home / "library").iterdir()) == []


def test_add_local_never_touches_the_fetcher_seam(home, monkeypatch):
    # no [ingest] section in config.toml at all — a missing fetcher must not matter
    monkeypatch.setattr(local, "duration_s", lambda path: 5)
    source = (home.parent / "no-fetcher-needed.mp4").resolve()
    source.write_bytes(b"bytes")
    assert run(home, "add", str(source)) == 0


def test_add_local_a_dangling_symlink_reads_as_no_video(home, monkeypatch):
    monkeypatch.setattr(local, "duration_s", lambda path: 5)
    source = (home.parent / "vanishing.mp4").resolve()
    source.write_bytes(b"bytes")
    assert run(home, "add", str(source)) == 0
    video_id = sources.local_id(source)
    entry = home / "library" / video_id
    assert fetch.has_video(entry)
    source.unlink()
    assert not fetch.has_video(entry)
    assert (entry / "meta.json").is_file()
