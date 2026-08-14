"""Durable evals: cli add on collections (SPEC-cli-003).

Boundary: the `tapedeck` executable; fetcher/transcriber/lister seams faked
through config.toml. The fetcher fake here is id-parametric ($TAPEDECK_VIDEO_ID),
so one script serves every video in a collection.
"""

import json

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
echo "$TAPEDECK_VIDEO_ID" >> "$TAPEDECK_HOME/whisper-log"
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


# --- SPEC-cli-003: a re-run of an unchanged collection does no work -----------
#
# "Skipped" has to mean skipped, not re-derived-into-the-same-bytes: on a 500-video
# channel the difference is one listing against two thousand no-op subprocesses.
# Since a re-derivation lands the same content, these evals mark each derived
# artifact by hand after the first sweep — anything that re-runs the chain wipes
# the mark, and the seam logs say whether the fetcher or the transcriber ran.

MARK = "\n<!-- edited by hand between sweeps -->\n"


def mark_derived(home, ids=IDS):
    """Fingerprint the derived layer so a re-derivation is visible."""
    for vid in ids:
        page = home / "archive" / f"{vid}.md"
        page.write_text(page.read_text() + MARK)
        transcript = home / "library" / vid / "transcript.json"
        doc = json.loads(transcript.read_text())
        doc["hand_mark"] = True
        transcript.write_text(json.dumps(doc, indent=2))


def derived_intact(home, vid):
    page = home / "archive" / f"{vid}.md"
    doc = json.loads((home / "library" / vid / "transcript.json").read_text())
    return MARK in page.read_text() and doc.get("hand_mark") is True


def test_a_second_sweep_of_an_unchanged_collection_derives_nothing(home):
    set_collection_pipeline(home)
    assert run_cli(["add", PLAYLIST], home).returncode == 0
    mark_derived(home)
    whisper_runs = (home / "whisper-log").read_text() if (home / "whisper-log").exists() else ""

    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    assert (home / "fetch-log").read_text().split() == list(IDS), "nothing was re-fetched"
    for vid in IDS:
        assert derived_intact(home, vid), f"{vid} was re-derived on an unchanged sweep"
    after = (home / "whisper-log").read_text() if (home / "whisper-log").exists() else ""
    assert after == whisper_runs, "the transcriber ran again on a complete video"
    assert "already present" in r.stdout


def test_an_incomplete_entry_is_still_re_derived(home):
    set_collection_pipeline(home)
    assert run_cli(["add", PLAYLIST], home).returncode == 0
    mark_derived(home)
    (home / "archive" / "bbbbbbbbbbb.md").unlink()

    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    assert (home / "archive" / "bbbbbbbbbbb.md").is_file(), "the missing page must come back"
    for vid in ("aaaaaaaaaaa", "ccccccccccc"):
        assert derived_intact(home, vid), f"{vid} was complete and must have been left alone"
    assert (home / "fetch-log").read_text().split() == list(IDS), "its media was still there"


def test_an_entry_holding_only_a_partial_download_is_not_present(home):
    """`video.part` is a fetch in flight, never the video (SPEC-ingest-001) — the
    cli must reach ingest's verdict, not its own."""
    set_collection_pipeline(home)
    assert run_cli(["add", PLAYLIST], home).returncode == 0
    mark_derived(home)
    entry = home / "library" / "bbbbbbbbbbb"
    (entry / "video.mp4").unlink()
    (entry / "video.part").write_bytes(b"half a download")

    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    assert (home / "fetch-log").read_text().split() == [*IDS, "bbbbbbbbbbb"], (
        "an entry with only video.part has no video: the sweep must re-fetch it"
    )
    assert (entry / "video.mp4").is_file()
    assert "1 added" in r.stdout, (
        "the sweep counted a partial download as a video already present"
    )
    for vid in ("aaaaaaaaaaa", "ccccccccccc"):
        assert derived_intact(home, vid), f"{vid} was complete and must have been left alone"
