"""Ephemeral unit tests for cli's own pure logic — disposable, not the
acceptance criteria (system/evals/cli/ is)."""

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


# --- SPEC-cli-011: the detached hand-off ----------------------------------


def test_handoff_does_nothing_with_no_filed_ids(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        '[wiki]\nmaintainer_command = "sh -c :"\n'
    )
    pipeline._handoff_wiki_filing(tmp_path, [])
    assert capsys.readouterr().err == ""


def test_handoff_is_silent_and_inert_when_auto_is_false(tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        '[wiki]\nauto = false\nmaintainer_command = "sh -c :"\n'
    )
    pipeline._handoff_wiki_filing(tmp_path, ["dQw4w9WgXcQ"])
    assert capsys.readouterr().err == ""


def test_handoff_names_the_missing_seam_and_spawns_nothing(tmp_path, capsys, monkeypatch):
    (tmp_path / "config.toml").write_text("[wiki]\nauto = true\n")
    spawned = []
    monkeypatch.setattr(
        pipeline.components, "spawn_detached", lambda *a, **k: spawned.append(a)
    )
    pipeline._handoff_wiki_filing(tmp_path, ["dQw4w9WgXcQ"])
    err = capsys.readouterr().err
    assert "maintainer" in err.lower()
    assert not spawned


def test_handoff_spawns_the_worker_and_announces_it(tmp_path, capsys, monkeypatch):
    (tmp_path / "config.toml").write_text(
        '[wiki]\nmaintainer_command = "sh -c :"\n'
    )
    spawned = []
    monkeypatch.setattr(
        pipeline.components, "spawn_detached", lambda *a, **k: spawned.append(a)
    )
    pipeline._handoff_wiki_filing(tmp_path, ["aaaaaaaaaaa", "bbbbbbbbbbb"])
    err = capsys.readouterr().err.lower()
    assert "wiki" in err and "log" in err and "fail" not in err
    assert spawned == [("cli", [pipeline.FILING_WORKER_VERB, "aaaaaaaaaaa", "bbbbbbbbbbb"], tmp_path)]


def test_filing_worker_verb_is_not_a_real_id():
    assert not pipeline.components.VIDEO_ID.fullmatch(pipeline.FILING_WORKER_VERB)


def test_run_filing_worker_calls_wiki_file_wait_in_order(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        pipeline.components,
        "run_quiet",
        lambda module, args, home: calls.append((module, args, home)) or 0,
    )
    rc = pipeline.run_filing_worker(tmp_path, ["aaaaaaaaaaa", "bbbbbbbbbbb"])
    assert rc == 0
    assert calls == [
        ("wiki", ["file", "--wait", "aaaaaaaaaaa"], tmp_path),
        ("wiki", ["file", "--wait", "bbbbbbbbbbb"], tmp_path),
    ]


def test_run_filing_worker_keeps_going_after_one_failure(tmp_path, monkeypatch):
    calls = []

    def fake_run_quiet(module, args, home):
        calls.append(args[-1])
        return 3 if args[-1] == "bbbbbbbbbbb" else 0

    monkeypatch.setattr(pipeline.components, "run_quiet", fake_run_quiet)
    pipeline.run_filing_worker(tmp_path, ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
    assert calls == ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]


def test_internal_worker_verb_bypasses_argparse():
    """main.py must intercept the worker verb before build_parser ever sees
    it — otherwise it would need to be a real subcommand, on the surface."""
    from cli import main as main_module

    _, subparsers = main_module.build_parser()
    assert pipeline.FILING_WORKER_VERB not in subparsers
