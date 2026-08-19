"""Ephemeral unit tests — disposable, not part of the durable evals."""

from pathlib import Path

from cli import doctor, home, pipeline


def test_head_skips_env_assignments():
    assert doctor._head("HF_HUB_OFFLINE=1 parakeet-mlx --flag") == "parakeet-mlx"
    assert doctor._head("sh /nowhere/whisper.sh --model large") == "sh"


def test_config_template_renders():
    text = home._config_text()
    assert "[wiki]" in text
    assert "maintainer_command" in text


def test_is_complete_false_for_missing_entry(tmp_path):
    (tmp_path / "library").mkdir()
    (tmp_path / "archive").mkdir()
    assert pipeline.is_complete(tmp_path, "dQw4w9WgXcQ") is False
