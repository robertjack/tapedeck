"""Durable evals: cli add on collections (SPEC-cli-003).

Boundary: the `tapedeck` executable; fetcher/transcriber/lister seams faked
through config.toml. The fetcher fake here is id-parametric ($TAPEDECK_VIDEO_ID),
so one script serves every video in a collection.
"""

from conftest import run_cli

FETCH_ANY = """#!/bin/sh
echo "$TAPEDECK_VIDEO_ID" >> "$TAPEDECK_HOME/fetch-log"
printf 'fake video bytes' > "$TAPEDECK_DEST/video.mp4"
cat > "$TAPEDECK_DEST/info.json" <<JSON
{"id": "$TAPEDECK_VIDEO_ID", "title": "Video $TAPEDECK_VIDEO_ID",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID"}
JSON
"""
FETCH_FAIL_MIDDLE = """#!/bin/sh
if [ "$TAPEDECK_VIDEO_ID" = "bbbbbbbbbbb" ]; then exit 1; fi
""" + FETCH_ANY.replace("#!/bin/sh\n", "")
WHISPER_OK = """#!/bin/sh
cat > "$TAPEDECK_OUT" <<'JSON'
{"language": "en", "segments": [
  {"start": 0.0, "end": 4.5, "text": " Fixture speech about regeneration."}
]}
JSON
"""
LIST_THREE = """#!/bin/sh
printf '%s\\n' aaaaaaaaaaa bbbbbbbbbbb ccccccccccc
"""

PLAYLIST = "https://www.youtube.com/playlist?list=PLtestfixture01"
IDS = ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")


def set_collection_pipeline(home, fetch_body=FETCH_ANY):
    fetch = home / "fetch.sh"
    fetch.write_text(fetch_body)
    lister = home / "lister.sh"
    lister.write_text(LIST_THREE)
    whisper = home / "whisper.sh"
    whisper.write_text(WHISPER_OK)
    (home / "config.toml").write_text(
        f'[ingest]\nfetcher_command = "sh {fetch}"\nlister_command = "sh {lister}"\n\n'
        f'[transcribe]\ntranscriber_command = "sh {whisper}"\nmodel = "fixture/whisper-0"\n'
    )


def test_add_playlist_adds_every_video(home):
    set_collection_pipeline(home)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    for vid in IDS:
        assert (home / "library" / vid / "transcript.json").is_file(), vid
        assert (home / "archive" / f"{vid}.md").is_file(), vid


def test_add_playlist_survives_one_failure(home):
    set_collection_pipeline(home, FETCH_FAIL_MIDDLE)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 1, "a failed video must fail the sweep's exit code"
    assert not (home / "library" / "bbbbbbbbbbb").exists()
    for vid in ("aaaaaaaaaaa", "ccccccccccc"):
        assert (home / "library" / vid / "meta.json").is_file(), (
            f"{vid} must be added despite the earlier failure"
        )
    assert "bbbbbbbbbbb" in r.stderr, "the failure must be reported"


def test_add_playlist_is_idempotent(home):
    set_collection_pipeline(home)
    assert run_cli(["add", PLAYLIST], home).returncode == 0
    assert run_cli(["add", PLAYLIST], home).returncode == 0
    fetched = (home / "fetch-log").read_text().split()
    assert sorted(fetched) == sorted(IDS), "re-running must skip existing videos"


def test_force_on_a_collection_is_a_usage_error(home):
    set_collection_pipeline(home)
    assert run_cli(["add", PLAYLIST, "--force"], home).returncode == 2
