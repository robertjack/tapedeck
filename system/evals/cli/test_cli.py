"""Durable evals: the tapedeck CLI (SPEC-cli-001, contracts/cli-surface.md).

Boundary: the `tapedeck` executable (override via $TAPEDECK_BIN), home via
$TAPEDECK_HOME. The cli orchestrates `add` through each component's module CLI,
in order: `python -m ingest add <url>` -> `python -m transcribe run <id>` ->
`python -m archive render <id>` -> `python -m index update <id>` — reusing the
same subprocess boundaries these components are evaluated at.
"""

import json

from conftest import run_cli

FETCH_OK = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/fetch-count"
printf 'fake video bytes' > "$TAPEDECK_DEST/video.mp4"
cat > "$TAPEDECK_DEST/info.json" <<'JSON'
{"id": "dQw4w9WgXcQ", "title": "Test Video: Building Things",
 "uploader": "Fixture Channel", "upload_date": "20260115", "duration": 720,
 "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
 "chapters": [{"title": "Intro", "start_time": 0},
              {"title": "The Core Idea", "start_time": 95}]}
JSON
"""
WHISPER_OK = """#!/bin/sh
cat > "$TAPEDECK_OUT" <<'JSON'
{"language": "en", "segments": [
  {"start": 0.0, "end": 4.5, "text": " Welcome to the fixture show."},
  {"start": 96.0, "end": 103.5, "text": " The core idea is regeneration."}
]}
JSON
"""

SUBCOMMANDS = (
    "add", "search", "ask", "list", "show", "reindex", "rm",
    "retranscribe", "adapt-parakeet",
)


def set_pipeline(home):
    fetch = home / "fetch.sh"
    fetch.write_text(FETCH_OK)
    whisper = home / "whisper.sh"
    whisper.write_text(WHISPER_OK)
    (home / "config.toml").write_text(
        f'[ingest]\nfetcher_command = "sh {fetch}"\n\n'
        f'[transcribe]\ntranscriber_command = "sh {whisper}"\nmodel = "fixture/whisper-0"\n'
    )


def test_help_lists_every_subcommand(home):
    r = run_cli(["--help"], home)
    assert r.returncode == 0
    for cmd in SUBCOMMANDS:
        assert cmd in r.stdout, f"{cmd!r} missing from tapedeck --help"


def test_every_subcommand_has_help(home):
    for cmd in SUBCOMMANDS:
        r = run_cli([cmd, "--help"], home)
        assert r.returncode == 0, f"tapedeck {cmd} --help failed: {r.stderr}"


def test_unknown_subcommand_exits_2(home):
    assert run_cli(["bogus"], home).returncode == 2


def test_first_run_scaffolds_home_and_config(tmp_path):
    home = tmp_path / "fresh" / "deck"  # does not exist yet
    r = run_cli(["list"], home)
    assert r.returncode == 0, r.stderr
    cfg = (home / "config.toml").read_text()
    for tool in ("yt-dlp", "mlx_whisper", "claude"):
        assert tool in cfg, f"first-run config.toml missing default for {tool}"
    assert "librarian_command" in cfg, "first-run config must configure the librarian seam"
    assert (home / "library").is_dir()
    brief = (home / "CLAUDE.md").read_text()
    assert "not in the library" in brief, "librarian brief must carry the grounding rule"
    assert "cite" in brief.lower()


def test_first_run_defaults_carry_the_battle_tested_seams(tmp_path):
    # LESSON-0001 / LESSON-0002: a fresh install ships the fixes — it never
    # re-suffers the AV1 403 or the large-v3 repetition loop.
    home = tmp_path / "fresh" / "deck"
    assert run_cli(["list"], home).returncode == 0
    cfg = (home / "config.toml").read_text()
    assert "vcodec^=avc1" in cfg, "default fetcher must prefer h264 (YouTube 403s AV1)"
    assert "height<=1080" in cfg
    assert "large-v3-turbo" in cfg, "default whisper model is large-v3-turbo"
    assert "--condition-on-previous-text False" in cfg, "repetition-loop guard missing"
    assert "mlx-whisper/large-v3-turbo" in cfg, "model label must name the real config"
    assert "lister_command" in cfg, "collections need the lister seam visible"
    assert "--flat-playlist" in cfg
    assert "adapt-parakeet" in cfg, "the parakeet alternative must be documented"


def test_add_runs_the_full_pipeline(home):
    set_pipeline(home)
    r = run_cli(["add", "https://youtu.be/dQw4w9WgXcQ"], home)
    assert r.returncode == 0, r.stderr
    lib = home / "library" / "dQw4w9WgXcQ"
    for f in ("video.mp4", "meta.json", "transcript.json"):
        assert (lib / f).is_file(), f"pipeline did not produce {f}"
    assert (home / "archive" / "dQw4w9WgXcQ.md").is_file()
    rs = run_cli(["search", "fixture", "--json"], home)
    assert rs.returncode == 0, rs.stderr
    results = json.loads(rs.stdout)
    assert results and results[0]["video_id"] == "dQw4w9WgXcQ"


def test_add_is_idempotent(home):
    set_pipeline(home)
    assert run_cli(["add", "dQw4w9WgXcQ"], home).returncode == 0
    assert run_cli(["add", "dQw4w9WgXcQ"], home).returncode == 0
    assert (home / "fetch-count").read_text().count("run") == 1
    assert len(list((home / "library").iterdir())) == 1


def test_list_and_show(home):
    set_pipeline(home)
    run_cli(["add", "dQw4w9WgXcQ"], home)
    rl = run_cli(["list"], home)
    assert rl.returncode == 0
    assert "dQw4w9WgXcQ" in rl.stdout and "Test Video" in rl.stdout
    rs = run_cli(["show", "dQw4w9WgXcQ"], home)
    assert rs.returncode == 0
    assert "Fixture Channel" in rs.stdout
    assert run_cli(["show", "nosuchvid00"], home).returncode == 2


def test_reindex_via_cli(home):
    set_pipeline(home)
    run_cli(["add", "dQw4w9WgXcQ"], home)
    (home / "tapedeck.db").unlink()
    assert run_cli(["reindex"], home).returncode == 0
    results = json.loads(run_cli(["search", "regeneration", "--json"], home).stdout)
    assert results and results[0]["video_id"] == "dQw4w9WgXcQ"


def test_garbage_url_exits_2(home):
    set_pipeline(home)
    assert run_cli(["add", "https://example.com/nope"], home).returncode == 2


ANSWER_OK = """#!/bin/sh
cat > /dev/null
printf 'It is about regeneration [1].\\n'
"""


def test_ask_end_to_end_through_the_executable(home):
    # the full brain: add a video, then ask about it — cli delegates to the ask
    # component (python -m ask run "<question>" [-k N] [--fast]); fast mode here
    # so the pipeline's citation contract is exercised through the executable
    set_pipeline(home)
    answer = home / "answer.sh"
    answer.write_text(ANSWER_OK)
    with (home / "config.toml").open("a") as fh:
        fh.write(f'\n[ask]\nanswerer_command = "sh {answer}"\n')
    assert run_cli(["add", "dQw4w9WgXcQ"], home).returncode == 0
    r = run_cli(["ask", "what is the core idea", "--fast"], home)
    assert r.returncode == 0, r.stderr
    assert "It is about regeneration [1]" in r.stdout
    assert "Sources:" in r.stdout
    assert "watch?v=dQw4w9WgXcQ&t=95s" in r.stdout
