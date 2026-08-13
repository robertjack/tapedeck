"""Durable evals: tapedeck rm (SPEC-cli-002).

Full removal by default; --media-only reclaims disk while keeping the knowledge.
Never touches any other video's data.
"""

import json

from conftest import PLAIN_META, add_video, run_cli, write_archive_page
from test_cli import set_pipeline

BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]


def added(home):
    set_pipeline(home)
    assert run_cli(["add", "dQw4w9WgXcQ"], home).returncode == 0


def search_json(home, query):
    r = run_cli(["search", query, "--json"], home)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_rm_removes_the_video_everywhere(home):
    added(home)
    r = run_cli(["rm", "dQw4w9WgXcQ"], home)
    assert r.returncode == 0, r.stderr
    assert not (home / "library" / "dQw4w9WgXcQ").exists()
    assert not (home / "archive" / "dQw4w9WgXcQ.md").exists()
    assert search_json(home, "fixture") == []
    assert "dQw4w9WgXcQ" not in run_cli(["list"], home).stdout


def test_rm_media_only_keeps_the_knowledge(home):
    added(home)
    r = run_cli(["rm", "dQw4w9WgXcQ", "--media-only"], home)
    assert r.returncode == 0, r.stderr
    lib = home / "library" / "dQw4w9WgXcQ"
    assert not (lib / "video.mp4").exists()
    for kept in ("meta.json", "transcript.json"):
        assert (lib / kept).is_file(), f"{kept} should survive --media-only"
    assert (home / "archive" / "dQw4w9WgXcQ.md").is_file()
    results = search_json(home, "fixture")
    assert results and results[0]["video_id"] == "dQw4w9WgXcQ"


def test_rm_never_touches_other_videos(home):
    added(home)
    add_video(home, PLAIN_META, [{"start": 2.0, "end": 6.0, "text": "sourdough"}])
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    assert run_cli(["reindex"], home).returncode == 0
    assert run_cli(["rm", "dQw4w9WgXcQ"], home).returncode == 0
    assert (home / "library" / "plainvide00").is_dir()
    assert (home / "archive" / "plainvide00.md").is_file()
    results = search_json(home, "sourdough")
    assert results and results[0]["video_id"] == "plainvide00"
    assert search_json(home, "fixture") == []


def test_rm_unknown_id_exits_2(home):
    added(home)
    r = run_cli(["rm", "nosuchvid00"], home)
    assert r.returncode == 2
    assert "nosuchvid00" in r.stderr
