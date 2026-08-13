"""Ephemeral unit tests for cli — disposable, regenerated with the component.

They cover what the durable evals reach only indirectly: the first-run scaffold's
exact content and its refusal to overwrite, the layout helpers the verbs share,
the catalogue's ordering and tolerance of a damaged entry, and the two sweeps —
a collection (SPEC-cli-003) and a model upgrade (SPEC-cli-004) — counted and
survived. The subprocess boundary to the other components is stubbed here; the
durable evals drive the real one.
"""

import json
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from cli import components, home, library, main  # noqa: E402

ID = "dQw4w9WgXcQ"
OTHER = "plainvide00"
PLAYLIST = "https://www.youtube.com/playlist?list=PLtest"
META = {
    "id": ID,
    "title": "Test Video",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": f"https://www.youtube.com/watch?v={ID}",
}


class Done:
    """What subprocess.run gives back, as much of it as the cli reads."""

    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "deck"))
    return home.resolve()


def entry(deck, video_id=ID, meta=META, transcript=True, video=True, model="fixture/whisper-0"):
    where = home.entry(deck, video_id)
    where.mkdir(parents=True, exist_ok=True)
    if video:
        (where / "video.mp4").write_bytes(b"\x00fixture")
    if meta is not None:
        (where / "meta.json").write_text(json.dumps({**meta, "id": video_id}))
    if transcript:
        (where / "transcript.json").write_text(
            json.dumps({"video_id": video_id, "model": model, "segments": []})
        )
    return where


def record(monkeypatch, outcome=lambda module, args: Done()):
    """Stub the component boundary; return the list of (module, args) calls made."""
    calls = []

    def fake(module, args, home_dir, capture=False):
        calls.append((module, list(args)))
        return outcome(module, args)

    monkeypatch.setattr(components, "run", fake)
    return calls


# ---------------------------------------------------------------- the scaffold


def test_first_run_creates_the_home_and_both_files(deck):
    assert (deck / "library").is_dir() and (deck / "archive").is_dir()
    assert (deck / "config.toml").is_file() and (deck / "CLAUDE.md").is_file()


def test_scaffolded_config_is_valid_toml_with_every_seam(deck):
    config = tomllib.loads((deck / "config.toml").read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    assert "--flat-playlist" in config["ingest"]["lister_command"]
    assert "mlx_whisper" in config["transcribe"]["transcriber_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"
    assert "claude" in config["ask"]["librarian_command"]
    assert "claude" in config["ask"]["answerer_command"]


def test_scaffolded_config_carries_the_battle_tested_defaults(deck):
    text = (deck / "config.toml").read_text()
    assert "vcodec^=avc1" in text and "height<=1080" in text  # LESSON-0001
    assert "--condition-on-previous-text False" in text  # LESSON-0002


def test_scaffolded_config_documents_the_parakeet_alternative(deck):
    text = (deck / "config.toml").read_text()
    assert "# transcriber_command = 'parakeet-mlx" in text
    assert "tapedeck adapt-parakeet" in text
    assert "# model = 'parakeet-mlx/tdt-0.6b-v3'" in text
    # Commented out, so the whisper default is still what a fresh install runs.
    config = tomllib.loads(text)
    assert "parakeet" not in config["transcribe"]["transcriber_command"]


def test_the_brief_carries_the_grounding_rules(deck):
    brief = (deck / "CLAUDE.md").read_text()
    assert "not in the library" in brief
    assert "watch?v=<video-id>&t=<seconds>s" in brief


def test_scaffolding_never_overwrites(deck):
    (deck / "config.toml").write_text("[ingest]\nfetcher_command = 'mine'\n")
    (deck / "CLAUDE.md").write_text("mine")
    assert home.resolve() == deck
    assert "mine" in (deck / "config.toml").read_text()
    assert (deck / "CLAUDE.md").read_text() == "mine"


def test_toml_value_survives_a_command_with_quotes():
    assert home.toml_value('a "b"') == "'a \"b\"'"
    assert tomllib.loads(f"c = {home.toml_value(chr(39) + 'x')}")["c"] == "'x"


def test_home_env_wins_over_the_default(tmp_path, monkeypatch):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "elsewhere"))
    assert home.resolve() == tmp_path / "elsewhere"


# ------------------------------------------------------------ layout helpers


def test_media_finds_the_video_and_not_its_sidecars(deck):
    where = entry(deck)
    (where / "video.info.json").write_text("{}")
    (where / "thumb.jpg").write_bytes(b"")
    assert [p.name for p in home.media(where)] == ["video.mp4"]


def test_ingested_needs_both_the_video_and_the_metadata(deck):
    assert not home.ingested(deck, ID)
    entry(deck, meta=None)
    assert not home.ingested(deck, ID)
    entry(deck)
    assert home.ingested(deck, ID)


def test_entries_skips_dotted_directories_and_files(deck):
    entry(deck)
    (deck / "library" / ".staging").mkdir()
    (deck / "library" / "stray.txt").write_text("")
    assert home.entries(deck) == [ID]


# ------------------------------------------------------------- list and show


def test_catalogue_is_newest_first_and_skips_a_damaged_entry(deck, capsys):
    entry(deck)
    entry(deck, OTHER, {**META, "upload_date": "2026-02-02", "title": "Sourdough"})
    entry(deck, "brokenvid00", meta=None)
    assert [video["id"] for video in library.catalogue(deck)] == [OTHER, ID]
    assert "brokenvid00" in capsys.readouterr().err


def test_show_json_names_every_artifact(deck, capsys):
    entry(deck)
    home.page(deck, ID).write_text("# page")
    assert library.show(deck, ID, as_json=True) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "Test Video"
    assert payload["archive"].endswith(f"{ID}.md")
    assert payload["media"].endswith("video.mp4")


def test_show_unknown_id_is_a_usage_error(deck):
    assert library.show(deck, "nosuchvid00", as_json=False) == 2
    assert library.show(deck, "not-an-id", as_json=False) == 2


def test_hms_tolerates_a_hand_edited_duration():
    assert library.hms(3725) == "1:02:05"
    assert library.hms(None) == ""


# ------------------------------------------------------------------- removal


def test_rm_deletes_the_page_before_updating_the_index(deck, monkeypatch):
    entry(deck)
    home.page(deck, ID).write_text("# page")
    seen = []

    def fake(module, args, home_dir, capture=False):
        seen.append((module, args, home.page(deck, ID).exists()))
        return Done()

    monkeypatch.setattr(components, "run", fake)
    assert library.remove(deck, ID, media_only=False) == 0
    assert seen == [("index", ["update", ID], False)]
    assert not home.entry(deck, ID).exists()


def test_rm_media_only_keeps_everything_derived(deck):
    where = entry(deck)
    assert library.remove(deck, ID, media_only=True) == 0
    assert not (where / "video.mp4").exists()
    assert (where / "transcript.json").is_file() and (where / "meta.json").is_file()


def test_rm_unknown_id_is_a_usage_error(deck):
    assert library.remove(deck, "nosuchvid00", media_only=False) == 2


# --------------------------------------------------------------- add and sweep


def test_add_one_runs_the_chain_in_order(deck, monkeypatch):
    calls = record(monkeypatch, lambda module, args: Done(stdout=str(home.entry(deck, ID))))
    assert components.add_one(deck, ID, force=False) == 0
    assert [module for module, _ in calls] == ["ingest", "transcribe", "archive", "index"]
    assert calls[1][1] == ["run", ID]


def test_force_reaches_the_transcript_too(deck, monkeypatch):
    calls = record(monkeypatch, lambda module, args: Done(stdout=str(home.entry(deck, ID))))
    assert components.add_one(deck, ID, force=True) == 0
    assert calls[0][1] == ["add", ID, "--force"]
    assert calls[1][1] == ["run", ID, "--force"]


def test_a_stage_failure_stops_the_chain_with_its_own_code(deck, monkeypatch):
    def outcome(module, args):
        if module == "transcribe":
            return Done(returncode=1)
        return Done(stdout=str(home.entry(deck, ID)))

    calls = record(monkeypatch, outcome)
    assert components.add_one(deck, ID, force=False) == 1
    assert [module for module, _ in calls] == ["ingest", "transcribe"]


def test_add_refuses_a_target_that_is_neither_video_nor_collection(deck, monkeypatch):
    calls = record(monkeypatch)
    assert components.add(deck, "https://example.com/nope", force=False) == 2
    assert calls == []


def test_force_on_a_collection_is_refused_before_any_listing(deck, monkeypatch):
    calls = record(monkeypatch)
    assert components.add(deck, PLAYLIST, force=True) == 2
    assert calls == []


def test_sweep_counts_added_skipped_and_failed(deck, monkeypatch, capsys):
    entry(deck, OTHER)  # already present: the sweep must skip its fetch
    listing = f"{ID}\n{OTHER}\nbadcatvide0\n"

    def outcome(module, args):
        if args[0] == "expand":
            return Done(stdout=listing)
        if args[0] == "add" and args[1] == "badcatvide0":
            return Done(returncode=1)
        return Done(stdout=str(home.entry(deck, args[1])))

    record(monkeypatch, outcome)
    assert components.add(deck, PLAYLIST, force=False) == 1
    out, err = capsys.readouterr()
    assert "1 added, 1 already present, 1 failed" in out
    assert "badcatvide0" in err


def test_a_listing_that_fails_is_not_a_sweep(deck, monkeypatch):
    calls = record(monkeypatch, lambda module, args: Done(returncode=1))
    assert components.add(deck, PLAYLIST, force=False) == 1
    assert calls == [("ingest", ["expand", PLAYLIST])]


# ------------------------------------------------------------- retranscribe


def configure(deck, model="fixture/whisper-2"):
    (deck / "config.toml").write_text(
        f'[transcribe]\ntranscriber_command = "sh whisper.sh"\nmodel = "{model}"\n'
    )


def test_retranscribe_picks_only_superseded_labels(deck, monkeypatch, capsys):
    configure(deck)
    entry(deck, ID, model="fixture/whisper-0")
    entry(deck, OTHER, model="fixture/whisper-2")
    calls = record(monkeypatch)
    assert components.retranscribe(deck, dry_run=False) == 0
    assert [args[1] for _, args in calls] == [ID, ID, ID]
    assert calls[0][1] == ["run", ID, "--force"]
    assert "1 re-transcribed with fixture/whisper-2, 0 failed" in capsys.readouterr().out


def test_retranscribe_sweeps_in_an_entry_with_no_transcript(deck, monkeypatch):
    configure(deck)
    entry(deck, ID, transcript=False)
    calls = record(monkeypatch)
    assert components.retranscribe(deck, dry_run=False) == 0
    assert calls[0] == ("transcribe", ["run", ID, "--force"])


def test_retranscribe_with_every_label_current_is_a_no_op(deck, monkeypatch):
    configure(deck)
    entry(deck, ID, model="fixture/whisper-2")
    calls = record(monkeypatch)
    assert components.retranscribe(deck, dry_run=False) == 0
    assert calls == []


def test_dry_run_prints_ids_to_stdout_and_runs_nothing(deck, monkeypatch, capsys):
    configure(deck)
    entry(deck, ID, model="fixture/whisper-0")
    entry(deck, OTHER, model="fixture/whisper-2")
    calls = record(monkeypatch)
    assert components.retranscribe(deck, dry_run=True) == 0
    out = capsys.readouterr().out
    assert out.split() == [ID]
    assert calls == []


def test_one_failure_does_not_stop_the_retranscribe_sweep(deck, monkeypatch, capsys):
    configure(deck)
    entry(deck, ID, model="old")
    entry(deck, OTHER, model="old")

    def outcome(module, args):
        return Done(returncode=1) if args[1] == ID else Done()

    record(monkeypatch, outcome)
    assert components.retranscribe(deck, dry_run=False) == 1
    out, err = capsys.readouterr()
    assert "1 re-transcribed with fixture/whisper-2, 1 failed" in out
    assert ID in err


def test_an_unconfigured_transcriber_is_a_usage_error(deck, monkeypatch):
    (deck / "config.toml").write_text("[ingest]\nfetcher_command = 'x'\n")
    calls = record(monkeypatch)
    assert components.retranscribe(deck, dry_run=False) == 2
    assert calls == []


# ------------------------------------------------------------------ the parser


def test_the_surface_is_exactly_the_contract():
    verbs = build_choices()
    assert verbs == {
        "add", "search", "ask", "list", "show", "reindex", "rm",
        "retranscribe", "adapt-parakeet",
    }


def build_choices():
    parser = main.build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and isinstance(action.choices, dict):
            return set(action.choices)
    raise AssertionError("no subcommands on the parser")


def test_every_verb_is_listed_in_help(capsys):
    with pytest.raises(SystemExit) as exit_code:
        main.build_parser().parse_args(["--help"])
    assert exit_code.value.code == 0
    printed = capsys.readouterr().out
    for verb in build_choices():
        assert verb in printed


def test_an_unknown_verb_exits_2():
    with pytest.raises(SystemExit) as exit_code:
        main.build_parser().parse_args(["bogus"])
    assert exit_code.value.code == 2


def test_adapt_parakeet_is_transcribes_filter_with_streams_inherited(deck, monkeypatch):
    seen = {}

    def fake(module, args, home_dir, capture=False):
        seen.update(module=module, args=args, capture=capture)
        return Done(returncode=3)

    monkeypatch.setattr(components, "run", fake)
    args = main.build_parser().parse_args(["adapt-parakeet"])
    assert main.dispatch(args, deck) == 3  # the child's code, unchanged
    assert seen == {"module": "transcribe", "args": ["from-parakeet"], "capture": False}


def test_optional_flags_are_passed_on_only_when_given(deck, monkeypatch):
    calls = record(monkeypatch)
    main.dispatch(main.build_parser().parse_args(["search", "a", "b"]), deck)
    main.dispatch(main.build_parser().parse_args(["ask", "why", "-k", "3", "--fast"]), deck)
    assert calls[0] == ("index", ["search", "a", "b"])
    assert calls[1] == ("ask", ["answer", "why", "-k", "3", "--fast"])
