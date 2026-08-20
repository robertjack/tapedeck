"""Ephemeral unit tests — disposable, not part of the durable evals."""

from pathlib import Path

from cli import components, doctor, home, pipeline


def test_head_skips_env_assignments():
    assert doctor._head("HF_HUB_OFFLINE=1 parakeet-mlx --flag") == "parakeet-mlx"
    assert doctor._head("sh /nowhere/whisper.sh --model large") == "sh"


def test_config_template_renders():
    text = home._config_text()
    assert "[wiki]" in text
    assert "maintainer_command" in text
    assert "auto = false" in text


def test_is_complete_false_for_missing_entry(tmp_path):
    (tmp_path / "library").mkdir()
    (tmp_path / "archive").mkdir()
    assert pipeline.is_complete(tmp_path, "dQw4w9WgXcQ") is False


def test_wiki_auto_absent_reads_false(tmp_path):
    (tmp_path / "config.toml").write_text("[wiki]\nmaintainer_command = 'sh -c :'\n")
    assert components.wiki_auto_enabled(tmp_path) is False


def test_wiki_auto_explicit_true(tmp_path):
    (tmp_path / "config.toml").write_text("[wiki]\nauto = true\n")
    assert components.wiki_auto_enabled(tmp_path) is True


def test_wiki_auto_no_config_file(tmp_path):
    assert components.wiki_auto_enabled(tmp_path) is False
