"""Ephemeral unit tests for the cli component.

These are disposable scaffolding, not the acceptance criteria — the durable
evaluations under system/evals/cli/ are. What they cover is what is cheap to
check in-process and expensive to check through a subprocess: the scaffold's
contents, the vocabulary the cli borrows, which arguments each verb forwards,
and the arithmetic of the sweeps.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ask.seams import BRIEF_NAME, CONFIG_NAME
from cli import Failure, components, home as home_module, library, main, pipeline, teach, views
from cli.library import Entry

META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video",
    "channel": "Fixture Channel",
    "upload_date": "2026-01-15",
    "duration_s": 720,
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}
VID = META["id"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return home_module.prepare(home_module.resolve())


def entry_with(home, video_id=VID, media="video.mp4", meta=True, transcript="fixture/whisper-0",
               page=True):
    path = home / "library" / video_id
    path.mkdir(parents=True, exist_ok=True)
    if media:
        (path / media).write_bytes(b"bytes")
    if meta:
        (path / "meta.json").write_text(json.dumps({**META, "id": video_id}))
    if transcript:
        (path / "transcript.json").write_text(
            json.dumps({"video_id": video_id, "model": transcript, "segments": []})
        )
    if page:
        (home / "archive" / f"{video_id}.md").write_text("# page\n")
    return Entry(home, video_id)


class Recorder:
    """Stands in for the component subprocesses: records, never runs."""

    def __init__(self, codes=None):
        self.calls = []
        self.codes = codes or {}

    def step(self, module, args, home):
        self.calls.append((module, args[0], args[1] if len(args) > 1 else None))
        return self.codes.get((module, args[1] if len(args) > 1 else None), 0)

    def output(self, module, args, home):
        self.calls.append((module, args[0], args[1] if len(args) > 1 else None))
        return 0, self.codes.get("listing", "")

    def forward(self, module, args, home):
        self.calls.append((module, args))
        return 0


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(components, "step", rec.step)
    monkeypatch.setattr(components, "output", rec.output)
    monkeypatch.setattr(components, "forward", rec.forward)
    return rec


# --- the first-run scaffold ---------------------------------------------------


def test_the_scaffold_publishes_every_seam(home):
    config = (home / CONFIG_NAME).read_text()
    for key in (
        "fetcher_command",
        "lister_command",
        "transcriber_command",
        "model",
        "librarian_command",
        "answerer_command",
    ):
        assert key in config, key
    assert (home / "library").is_dir() and (home / "archive").is_dir()


def test_the_scaffold_quotes_commands_the_shell_can_still_read(home):
    import tomllib

    config = tomllib.loads((home / CONFIG_NAME).read_text())
    assert config["ingest"]["fetcher_command"].startswith("yt-dlp")
    # The quoting in the format selector has to survive TOML untouched.
    assert '-f "bv*[vcodec^=avc1]' in config["ingest"]["fetcher_command"]
    assert config["transcribe"]["model"] == "mlx-whisper/large-v3-turbo"


def test_a_command_carrying_a_quote_falls_back_to_a_basic_string():
    assert home_module._toml("say 'hi'") == '"say \'hi\'"'
    assert home_module._toml('say "hi"') == '\'say "hi"\''


def test_the_scaffold_is_written_once(home):
    (home / CONFIG_NAME).write_text("# mine now\n")
    (home / BRIEF_NAME).write_text("# my brief\n")
    home_module.prepare(home)
    assert (home / CONFIG_NAME).read_text() == "# mine now\n"
    assert (home / BRIEF_NAME).read_text() == "# my brief\n"


def test_the_brief_carries_the_grounding_rules(home):
    brief = (home / BRIEF_NAME).read_text()
    assert "not in the library" in brief
    assert "cite" in brief.lower()


# --- the library, in the components' vocabulary -------------------------------


def test_a_part_file_is_not_a_video(home):
    entry = entry_with(home, media="video.part")
    assert entry.media() is None
    assert not entry.has_media()
    assert not entry.complete()


def test_complete_needs_all_four_artifacts(home):
    assert entry_with(home).complete()
    assert not entry_with(home, "bbbbbbbbbbb", page=False).complete()
    assert not entry_with(home, "ccccccccccc", transcript=None).complete()
    assert not entry_with(home, "ddddddddddd", meta=False).complete()
    assert not entry_with(home, "eeeeeeeeeee", media=None).complete()


def test_model_reads_the_transcripts_label(home):
    assert entry_with(home).model() == "fixture/whisper-0"
    assert entry_with(home, "bbbbbbbbbbb", transcript=None).model() is None


def test_unreadable_json_is_a_quieter_answer_not_a_crash(home):
    entry = entry_with(home)
    entry.meta_path.write_text("{not json")
    assert entry.meta() == {}


def test_media_only_removal_keeps_the_knowledge(home):
    entry = entry_with(home)
    (entry.path / "video.part").write_bytes(b"leftover")
    library.remove_media(entry)
    assert entry.media() is None
    assert entry.meta_path.is_file() and entry.transcript_path.is_file() and entry.page.is_file()


def test_full_removal_leaves_the_index_to_the_index(home, recorder):
    entry = entry_with(home)
    assert pipeline.remove(home, VID, media_only=False) == 0
    assert not entry.path.exists() and not entry.page.exists()
    assert (components.INDEX, "update", VID) in recorder.calls


def test_removing_what_is_not_here_is_a_usage_error(home, recorder):
    with pytest.raises(Failure) as caught:
        pipeline.remove(home, "nosuchvid00", media_only=False)
    assert caught.value.code == 2
    with pytest.raises(Failure):
        pipeline.remove(home, "not-an-id", media_only=False)


# --- add: one video, or a collection ------------------------------------------


def test_add_drives_the_chain_in_order(home, recorder):
    assert pipeline.add(home, "https://youtu.be/dQw4w9WgXcQ", force=False) == 0
    assert [call[0] for call in recorder.calls] == [
        components.INGEST,
        components.TRANSCRIBE,
        components.ARCHIVE,
        components.INDEX,
    ]


def test_force_reaches_ingest_for_one_video(home, recorder):
    pipeline.add(home, VID, force=True)
    assert recorder.calls[0] == (components.INGEST, "add", VID)


def test_force_on_a_collection_never_reaches_the_lister(home, recorder):
    with pytest.raises(Failure) as caught:
        pipeline.add(home, "https://www.youtube.com/playlist?list=PL1", force=True)
    assert caught.value.code == 2
    assert recorder.calls == []


def test_a_bad_target_is_ingests_verdict(home, recorder):
    from ingest.sources import BadRequest

    with pytest.raises(BadRequest):
        pipeline.add(home, "https://example.com/nope", force=False)


def test_a_sweep_skips_complete_videos_entirely(home, recorder, capsys):
    recorder.codes["listing"] = "aaaaaaaaaaa\nbbbbbbbbbbb\n"
    entry_with(home, "aaaaaaaaaaa")
    assert pipeline.sweep(home, "https://www.youtube.com/playlist?list=PL1") == 0
    touched = [call for call in recorder.calls if call[2] == "aaaaaaaaaaa"]
    assert touched == [], "a complete video must cost nothing at all"
    out = capsys.readouterr().out
    assert "1 added, 1 already present, 0 failed" in out


def test_one_failure_never_stops_a_sweep(home, recorder, capsys):
    recorder.codes["listing"] = "aaaaaaaaaaa\nbbbbbbbbbbb\nccccccccccc\n"
    recorder.codes[(components.INGEST, "bbbbbbbbbbb")] = 1
    assert pipeline.sweep(home, "https://www.youtube.com/playlist?list=PL1") == 1
    captured = capsys.readouterr()
    assert "bbbbbbbbbbb" in captured.err
    assert "2 added, 0 already present, 1 failed" in captured.out
    assert (components.INDEX, "update", "ccccccccccc") in recorder.calls


def test_a_listing_is_read_with_ingests_parser(home, recorder):
    recorder.codes["listing"] = "[youtube] listing…\naaaaaaaaaaa\naaaaaaaaaaa\n\n"
    assert pipeline.expand(home, "https://www.youtube.com/playlist?list=PL1") == ["aaaaaaaaaaa"]


# --- retranscribe -------------------------------------------------------------


def upgraded(home, model="fixture/whisper-2"):
    (home / CONFIG_NAME).write_text(
        f'[transcribe]\ntranscriber_command = "sh whisper.sh"\nmodel = "{model}"\n'
    )


def test_the_sweep_selects_only_superseded_labels(home):
    upgraded(home)
    entry_with(home, "aaaaaaaaaaa", transcript="fixture/whisper-0")
    entry_with(home, "bbbbbbbbbbb", transcript="fixture/whisper-2")
    redo, skipped = pipeline.select(home, "fixture/whisper-2")
    assert redo == ["aaaaaaaaaaa"]
    assert skipped == []


def test_the_sweep_reports_what_it_could_never_re_derive(home):
    entry_with(home, "aaaaaaaaaaa", media=None, transcript="fixture/whisper-0")
    (home / "library" / "reading-notes").mkdir()
    redo, skipped = pipeline.select(home, "fixture/whisper-2")
    assert redo == []
    assert any("aaaaaaaaaaa" in note for note in skipped)
    assert any("reading-notes" in note for note in skipped)


def test_a_missing_transcript_is_superseded_too(home):
    entry_with(home, "aaaaaaaaaaa", transcript=None)
    redo, _ = pipeline.select(home, "fixture/whisper-2")
    assert redo == ["aaaaaaaaaaa"]


def test_dry_run_prints_ids_and_nothing_else(home, recorder, capsys):
    upgraded(home)
    entry_with(home, "aaaaaaaaaaa", transcript="fixture/whisper-0")
    entry_with(home, "bbbbbbbbbbb", media=None, transcript="fixture/whisper-0")
    assert pipeline.retranscribe(home, dry_run=True) == 0
    captured = capsys.readouterr()
    assert captured.out.split() == ["aaaaaaaaaaa"]
    assert "bbbbbbbbbbb" in captured.err
    assert recorder.calls == []


def test_retranscribe_redoes_the_chain_below_the_video(home, recorder):
    upgraded(home)
    entry_with(home, "aaaaaaaaaaa", transcript="fixture/whisper-0")
    assert pipeline.retranscribe(home, dry_run=False) == 0
    assert recorder.calls == [
        (components.TRANSCRIBE, "run", "aaaaaaaaaaa"),
        (components.ARCHIVE, "render", "aaaaaaaaaaa"),
        (components.INDEX, "update", "aaaaaaaaaaa"),
    ]


def test_an_unconfigured_transcriber_is_a_usage_error(home):
    (home / CONFIG_NAME).write_text("# empty\n")
    from transcribe.transcriber import ConfigError

    with pytest.raises(ConfigError):
        pipeline.retranscribe(home, dry_run=True)


# --- list and show ------------------------------------------------------------


def test_list_json_is_one_row_per_video(home, capsys):
    entry_with(home)
    views.listing(home, as_json=True)
    rows = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in rows] == [VID]
    assert rows[0]["title"] == "Test Video"


def test_show_reports_a_missing_video_as_missing(home, capsys):
    entry_with(home, media="video.part")
    assert views.show(home, VID, as_json=True) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["media"] is None
    assert views.show(home, VID, as_json=False) == 0
    assert "video.part" not in capsys.readouterr().out


def test_show_of_an_unknown_id_is_a_usage_error(home):
    with pytest.raises(Failure) as caught:
        views.show(home, "nosuchvid00", as_json=False)
    assert caught.value.code == 2


def test_an_unknown_duration_is_not_zero_seconds():
    assert views._duration({"duration_s": 0}) == "unknown"
    assert views._duration({}) == "unknown"
    assert views._duration({"duration_s": 720}) == "0:12:00"


# --- help ---------------------------------------------------------------------


def build_choices():
    _, verbs = main.build()
    return verbs.choices


def test_the_tour_is_one_screen_and_names_the_everyday_verbs():
    out = io.StringIO()
    teach.teach(build_choices(), None, out=out)
    text = out.getvalue()
    assert len(text.splitlines()) <= 45
    for verb in ("add", "search", "ask", "list", "show", "retranscribe"):
        assert verb in text
    assert "\x1b" not in text


def test_a_verb_gets_its_usage_and_an_example():
    out = io.StringIO()
    teach.teach(build_choices(), "add", out=out)
    text = out.getvalue()
    assert "usage:" in text and "--force" in text
    assert "tapedeck add" in text


def test_every_verb_has_an_example():
    for verb in build_choices():
        assert verb in teach.EXAMPLES, f"{verb} has no worked example"


def test_the_manual_comes_out_verbatim_when_piped():
    out = io.StringIO()
    teach.teach(build_choices(), "manual", out=out)
    assert out.getvalue() == teach.manual_path().read_text(encoding="utf-8")


def test_an_unknown_topic_names_what_it_knows():
    with pytest.raises(Failure) as caught:
        teach.teach(build_choices(), "bogus", out=io.StringIO())
    assert caught.value.code == 2
    assert "manual" in str(caught.value)


def test_no_colour_when_nobody_is_looking(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setenv("NO_COLOR", "1")
    assert "\x1b" not in teach.paint(teach.TOUR, Terminal())
    monkeypatch.delenv("NO_COLOR")
    assert "\x1b" in teach.paint(teach.TOUR, Terminal())


# --- dispatch -----------------------------------------------------------------


def dispatched(argv, home):
    parser, verbs = main.build()
    return main.dispatch(parser.parse_args(argv), home, verbs.choices)


def test_search_forwards_flags_and_fences_the_query(home, recorder):
    dispatched(["search", "-k", "3", "--json", "why", "not"], home)
    module, args = recorder.calls[0]
    assert module == components.INDEX
    assert args == ["search", "-k", "3", "--json", "--", "why", "not"]


def test_ask_forwards_every_mode_flag(home, recorder):
    dispatched(["ask", "what", "--fast", "--video", VID, "-k", "4"], home)
    module, args = recorder.calls[0]
    assert module == components.ASK
    assert args == ["run", "-k", "4", "--fast", "--video", VID, "--", "what"]


def test_ask_without_flags_forwards_nothing_extra(home, recorder):
    dispatched(["ask", "what"], home)
    assert recorder.calls[0][1] == ["run", "--", "what"]


def test_adapt_parakeet_is_transcribes_filter(home, recorder):
    dispatched(["adapt-parakeet"], home)
    assert recorder.calls[0] == (components.TRANSCRIBE, ["from-parakeet"])


def test_reindex_is_the_index(home, recorder):
    dispatched(["reindex"], home)
    assert recorder.calls[0] == (components.INDEX, ["reindex"])


def test_the_bare_command_teaches(home, recorder, capsys):
    assert dispatched([], home) == 0
    assert "tapedeck add" in capsys.readouterr().out


def test_main_turns_a_failure_into_its_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path / "fresh"))
    assert main.main(["show", "nosuchvid00"]) == 2
    assert "nosuchvid00" in capsys.readouterr().err
    assert (tmp_path / "fresh" / CONFIG_NAME).is_file(), "the home is made on every run"
