"""Ephemeral unit tests for cli's own pure logic — disposable, not the
acceptance criteria (system/evals/cli/ is)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli import doctor, home, pipeline


def test_head_skips_environment_assignments():
    assert doctor.head("FOO=1 BAR=2 sh -c :") == "sh"


def test_head_plain_command():
    assert doctor.head("yt-dlp --flat-playlist") == "yt-dlp"


def test_head_all_assignments_is_none():
    assert doctor.head("FOO=1 BAR=2") is None


def test_ensure_home_is_idempotent(tmp_path):
    target = tmp_path / "deck"
    home.ensure_home(target)
    config_text = (target / "config.toml").read_text()
    (target / "config.toml").write_text(config_text + "\n# user edit\n")
    home.ensure_home(target)
    assert "# user edit" in (target / "config.toml").read_text()


def test_is_complete_requires_media_transcript_and_archive(tmp_path):
    vid = "dQw4w9WgXcQ"
    entry = tmp_path / "library" / vid
    entry.mkdir(parents=True)
    assert not pipeline._is_complete(tmp_path, vid)
    (entry / "video.mp4").write_bytes(b"x")
    (entry / "transcript.json").write_text("{}")
    assert not pipeline._is_complete(tmp_path, vid)
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / f"{vid}.md").write_text("# page")
    assert pipeline._is_complete(tmp_path, vid)


def test_wiki_auto_defaults_true_when_absent(tmp_path):
    (tmp_path / "config.toml").write_text("# no wiki section\n")
    assert pipeline._wiki_auto(tmp_path) is True


def test_wiki_auto_false_when_set(tmp_path):
    (tmp_path / "config.toml").write_text("[wiki]\nauto = false\n")
    assert pipeline._wiki_auto(tmp_path) is False
