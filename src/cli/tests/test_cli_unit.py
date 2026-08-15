"""Ephemeral unit tests for the cli component — disposable, and deliberately at
the seams the durable evals reach only through a subprocess: the scaffolded
config as data, the `[wiki] auto` default, the routing decision `main` makes
before argparse ever sees the argv, and doctor's row-building.
"""

import shlex
import tomllib
from pathlib import Path

import pytest

from cli import doctor, home, main, pipeline, teach, views
from wiki.seams import DEFAULT_MAINTAINER_COMMAND

MISSING = "cli-unit-no-such-tool-91f2"


# --- the first-run config ------------------------------------------------------


@pytest.fixture
def config():
    return tomllib.loads(home.config_text())


def test_the_scaffold_is_valid_toml_with_every_section(config):
    assert set(config) >= {"ingest", "transcribe", "ask", "wiki", "setup"}


def test_every_seam_doctor_checks_is_written_into_the_scaffold(config):
    for section, key, _ in doctor.SEAMS:
        assert isinstance(config[section][key], str) and config[section][key].strip(), (
            f"{section}.{key} is checked but never scaffolded"
        )


def test_the_wiki_seam_is_the_components_published_default(config):
    assert config["wiki"]["maintainer_command"] == DEFAULT_MAINTAINER_COMMAND


def test_auto_filing_ships_on_and_the_code_agrees_with_the_file(config):
    assert config["wiki"]["auto"] is home.AUTO_FILE_DEFAULT is True


def test_every_shipped_seam_head_has_a_remedy(config):
    heads = {"ffmpeg"}
    for section in ("ingest", "transcribe", "ask", "wiki"):
        for key, value in config[section].items():
            if key.endswith("_command"):
                heads.add(shlex.split(value)[0])
    assert not heads - set(config["setup"]["remedy"])


def test_the_scaffold_never_rewrites_what_is_already_there(tmp_path):
    deck = home.scaffold(tmp_path / "deck")
    (deck / home.CONFIG_NAME).write_text("# mine now\n")
    home.scaffold(deck)
    assert (deck / home.CONFIG_NAME).read_text() == "# mine now\n"


# --- `[wiki] auto`: an absent key reads what the scaffold writes ----------------


def write_config(home_dir: Path, text: str) -> Path:
    home_dir.mkdir(parents=True, exist_ok=True)
    (home_dir / home.CONFIG_NAME).write_text(text)
    return home_dir


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("[wiki]\n", True),
        ("[wiki]\nauto = true\n", True),
        ("[wiki]\nauto = false\n", False),
        ('[wiki]\nauto = "sometimes"\n', True),  # not a boolean, not an answer
        ("[ingest]\nfetcher_command = 'yt-dlp'\n", True),
        ("this is not toml at all [[[", True),
    ],
)
def test_auto_filing_reads_the_switch(tmp_path, text, expected):
    assert pipeline.auto_filing(write_config(tmp_path / "deck", text)) is expected


def test_the_scaffolded_config_files_by_default(tmp_path):
    assert pipeline.auto_filing(home.scaffold(tmp_path / "deck")) is True


# --- the note a failed filing owes the user ------------------------------------


def test_the_note_names_the_seam_when_there_is_none(tmp_path):
    note = pipeline.seam_note(write_config(tmp_path / "deck", "[wiki]\n"))
    assert "maintainer_command" in note and "not set" in note


def test_the_note_names_an_unresolvable_maintainer(tmp_path):
    deck = write_config(tmp_path / "deck", f"[wiki]\nmaintainer_command = '{MISSING} -p'\n")
    assert MISSING in pipeline.seam_note(deck)


def test_a_resolvable_maintainer_leaves_the_note_to_the_component(tmp_path):
    deck = write_config(tmp_path / "deck", "[wiki]\nmaintainer_command = 'sh -c :'\n")
    assert pipeline.seam_note(deck) == ""


def test_auto_false_never_reaches_the_component(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(pipeline.components, "stage", lambda *a, **k: ran.append(a) or 0)
    pipeline.file_into_wiki(write_config(tmp_path / "deck", "[wiki]\nauto = false\n"), "abc")
    assert ran == []


def test_auto_true_files_at_the_components_boundary(tmp_path, monkeypatch, capsys):
    calls = []

    def stage(module, args, where):
        calls.append((module, args))
        return 0

    monkeypatch.setattr(pipeline.components, "stage", stage)
    pipeline.file_into_wiki(write_config(tmp_path / "deck", ""), "dQw4w9WgXcQ")
    assert calls == [("wiki", ["file", "dQw4w9WgXcQ"])]
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "", "a filing that worked says nothing"


def test_a_failed_filing_is_one_note_on_stderr_and_nothing_on_stdout(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(pipeline.components, "stage", lambda *a, **k: 1)
    pipeline.file_into_wiki(write_config(tmp_path / "deck", "[wiki]\n"), "dQw4w9WgXcQ")
    captured = capsys.readouterr()
    assert captured.out == "", "nothing about the epilogue reaches add's stdout"
    assert "wiki" in captured.err.lower() and "dQw4w9WgXcQ" in captured.err
    assert "maintainer_command" in captured.err
    assert len([ln for ln in captured.err.splitlines() if ln.strip()]) == 1


# --- doctor: the seams decide the checks ---------------------------------------


def test_the_checks_are_emitted_in_the_pinned_order(tmp_path):
    rows = doctor.diagnose(home.scaffold(tmp_path / "deck"))
    assert [row["check"] for row in rows] == [
        "ingest.fetcher_command",
        "ingest.lister_command",
        "transcribe.transcriber_command",
        "ask.librarian_command",
        "ask.answerer_command",
        "wiki.maintainer_command",
        "ffmpeg",
        "home",
        "fts5",
        "platform",
    ]


def test_an_optional_seam_never_reaches_the_failed_list(tmp_path):
    deck = write_config(
        tmp_path / "deck",
        f"[ask]\nlibrarian_command = '{MISSING}'\n\n[wiki]\nmaintainer_command = '{MISSING}'\n",
    )
    diagnosis = doctor.diagnose(deck)
    rows = {row["check"]: row for row in diagnosis}
    for check in ("ask.librarian_command", "wiki.maintainer_command"):
        assert rows[check]["status"] == doctor.OPTIONAL
        assert rows[check]["missing"] == MISSING
    broken = [row["check"] for row in doctor.failed(diagnosis)]
    assert "ask.librarian_command" not in broken and "wiki.maintainer_command" not in broken


def test_the_wiki_reason_says_what_its_absence_costs(tmp_path):
    rows = {row["check"]: row for row in doctor.diagnose(write_config(tmp_path / "deck", ""))}
    detail = rows["wiki.maintainer_command"]["detail"].lower()
    assert "wiki" in detail and "add" in detail


def test_the_public_rows_carry_only_the_promised_keys(tmp_path):
    for row in doctor.public(doctor.diagnose(home.scaffold(tmp_path / "deck"))):
        assert set(row) == {"check", "status", "detail"}


# --- routing: everything after `wiki` is the component's -----------------------


def test_the_group_is_handed_over_whole(tmp_path, monkeypatch):
    handed = {}

    def passthrough(module, args, where):
        handed.update(module=module, args=args)
        return 7

    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    monkeypatch.setattr(main.components, "passthrough", passthrough)
    code = main.main(["wiki", "lint", "--json", "--anything-it-grows-tomorrow"])
    assert code == 7, "the child's exit code is tapedeck's"
    assert handed == {
        "module": "wiki",
        "args": ["lint", "--json", "--anything-it-grows-tomorrow"],
    }


def test_even_help_belongs_to_the_component(tmp_path, monkeypatch):
    handed = {}
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    monkeypatch.setattr(
        main.components,
        "passthrough",
        lambda module, args, where: handed.setdefault("args", args) and 0,
    )
    main.main(["wiki", "--help"])
    assert handed["args"] == ["--help"]


def test_routing_does_not_hijack_the_word_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    monkeypatch.setattr(
        main.components, "passthrough", lambda *a, **k: pytest.fail("routed a non-wiki verb")
    )
    assert main.main(["show", "wiki"]) == 2  # not a video id: a usage error


def test_the_surface_is_exactly_the_contracts(tmp_path):
    _, verbs = main.build_parser()
    assert set(verbs) == {
        "add", "search", "ask", "list", "show", "reindex", "rm", "retranscribe",
        "wiki", "adapt-parakeet", "doctor", "setup", "help",
    }


def test_every_verb_has_a_worked_example():
    _, verbs = main.build_parser()
    assert set(verbs) <= set(teach.EXAMPLES)


def test_help_wiki_names_the_group_and_its_subverbs(capsys):
    _, verbs = main.build_parser()
    teach.teach("wiki", verbs)
    out = capsys.readouterr().out
    assert "usage:" in out and "tapedeck wiki" in out
    for sub in ("file", "sync", "lint", "rebuild"):
        assert sub in out


# --- rm's one question of the wiki ---------------------------------------------


def test_the_filed_marker_is_the_path_the_contract_publishes(tmp_path):
    assert views.filed_page(tmp_path, "dQw4w9WgXcQ") == (
        tmp_path / "wiki" / "sources" / "dQw4w9WgXcQ.md"
    )
