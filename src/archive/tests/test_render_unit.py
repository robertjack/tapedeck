"""Ephemeral unit tests: the seams the durable evals cannot see from outside.

Disposable — the durable evals in system/evals/archive/ are the real contract.
Run with: uv run --with pytest pytest src/archive/tests -q
"""

import json

import pytest

import archive.__main__
from archive.__main__ import Failure, load_meta, load_transcript, main, render_one
from archive.render import BLOCK_S, _paragraphs, deep_link, hms, page, sections, yaml_scalar

META = {
    "id": "abcdefghijk",
    "title": "A Title",
    "channel": "Chan",
    "upload_date": "2026-03-04",
    "duration_s": 600,
    "url": "https://www.youtube.com/watch?v=abcdefghijk",
}


def seg(start, end, text):
    return {"start": start, "end": end, "text": text}


def transcript(segments):
    return {"video_id": META["id"], "model": "unit/fake", "segments": segments}


# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0:00:00"), (95, "0:01:35"), (610, "0:10:10"), (3661, "1:01:01"), (95.9, "0:01:35")],
)
def test_hms(seconds, expected):
    assert hms(seconds) == expected


def test_deep_link_floors_to_whole_seconds():
    assert deep_link(META["url"], 95.9) == "https://www.youtube.com/watch?v=abcdefghijk&t=95s"


def test_deep_link_opens_a_query_string_for_a_url_without_one():
    assert deep_link("file:///a/standup.mp4", 90) == "file:///a/standup.mp4?t=90s"


def test_deep_link_joins_an_existing_query_string():
    assert deep_link("https://x.test/watch?v=abc", 5) == "https://x.test/watch?v=abc&t=5s"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("abcdefghijk", "abcdefghijk"),
        ("Fixture Channel", "Fixture Channel"),
        ("2026-01-15", "2026-01-15"),
        ("https://x.test/a?b=c#d", "https://x.test/a?b=c#d"),
        ("Test Video: Building Things", '"Test Video: Building Things"'),
        ("2026", '"2026"'),
        ("NO", '"NO"'),
        ("", '""'),
        (" padded ", '" padded "'),
        ("- dashed", '"- dashed"'),
        ('say "hi"\nagain', '"say \\"hi\\"\\nagain"'),
        (720, "720"),
    ],
)
def test_yaml_scalar(value, expected):
    assert yaml_scalar(value) == expected


# --- sectioning -------------------------------------------------------------


def test_blocks_cover_the_longer_of_duration_and_transcript():
    meta = {**META, "duration_s": 600}
    late = [seg(0, 1, "a"), seg(910, 915, "b")]
    assert sections(meta, late) == [(0, ""), (300, ""), (600, ""), (900, "")]
    assert sections({**META, "duration_s": 0}, []) == [(0, "")]
    assert len(sections({**META, "duration_s": BLOCK_S}, [])) == 1


def test_chapters_are_sorted_and_deduped():
    meta = {**META, "chapters": [{"title": "Two", "start_s": 95.5}, {"title": "One", "start_s": 0}]}
    assert sections(meta, []) == [(0, "One"), (95, "Two")]
    dupes = {**META, "chapters": [{"title": "Keep", "start_s": 5}, {"title": "Drop", "start_s": 5}]}
    assert sections(dupes, []) == [(5, "Keep")]


def test_late_first_chapter_gets_an_untitled_lead_in_only_when_needed():
    meta = {**META, "chapters": [{"title": "Late", "start_s": 60}]}
    assert sections(meta, [seg(2, 5, "pre-roll")]) == [(0, ""), (60, "Late")]
    assert sections(meta, [seg(70, 75, "after")]) == [(60, "Late")]


def test_every_segment_lands_somewhere():
    meta = {**META, "chapters": [{"title": "Only", "start_s": 30}]}
    rendered = page(meta, transcript([seg(70, 75, "after the start")]))
    assert "after the start" in rendered


# --- paragraph anchors (SPEC-archive-002) ------------------------------------


def test_paragraphs_carry_their_own_first_segment_start():
    segs = [seg(2, 4, "first half"), seg(5, 8, "second half"), seg(60, 62, "after a gap")]
    assert _paragraphs(segs) == [(2, "first half second half"), (60, "after a gap")]


def test_page_anchors_each_paragraph_with_its_own_start_not_the_section_start():
    doc = transcript([seg(2, 4, "early words"), seg(310, 312, "late words")])
    body = page(META, doc)
    assert f"[0:00:02]({deep_link(META['url'], 2)}) early words" in body
    assert f"[0:05:10]({deep_link(META['url'], 310)}) late words" in body
    assert f"[0:00:00]({deep_link(META['url'], 0)}) early" not in body


def test_exactly_one_anchor_per_paragraph_line():
    doc = transcript([seg(0, 4, "one"), seg(60, 62, "two")])
    body = page(META, doc)
    paragraph_lines = [line for line in body.splitlines() if line.startswith("[")]
    assert len(paragraph_lines) == 2
    for line in paragraph_lines:
        assert line.count("](https://") == 1


# --- local (non-YouTube) addresses ------------------------------------------


def test_local_file_url_is_addressed_directly_no_youtube_knowledge():
    local = {**META, "channel": "", "url": "file:///Users/somebody/Footage/standup.mp4"}
    body = page(local, transcript([seg(2, 4, "hello")]))
    assert "youtube.com" not in body
    assert "[0:00:02](file:///Users/somebody/Footage/standup.mp4?t=2s) hello" in body


def test_empty_channel_leaves_no_dangling_separator_in_the_byline():
    local = {**META, "channel": "", "url": "file:///a/b.mp4"}
    body = page(local, transcript([seg(0, 1, "x")]))
    byline = next(line for line in body.splitlines() if "2026-03-04" in line)
    assert not byline.startswith("·") and " ·  · " not in byline


# --- page shape -------------------------------------------------------------


def test_page_is_deterministic_and_ends_with_one_newline():
    doc = transcript([seg(0, 2, "one"), seg(301, 303, "two")])
    first = page(META, doc)
    assert first == page(META, doc)
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_frontmatter_key_order():
    head = page(META, transcript([seg(0, 1, "x")])).split("---\n")[1]
    assert [line.split(":")[0] for line in head.strip().splitlines()] == [
        "id",
        "title",
        "channel",
        "upload_date",
        "duration_s",
        "url",
    ]


def test_paragraphs_break_on_silence_not_on_speech():
    doc = transcript(
        [seg(0, 4, "first half"), seg(5, 8, "second half"), seg(60, 62, "after a gap")]
    )
    body = page(META, doc)
    assert "first half second half" in body
    assert "after a gap" in body.split("first half second half")[1]


def test_segment_text_is_whitespace_normalised():
    doc = transcript([seg(0, 4, "  ragged\n  whisper   text ")])
    assert "ragged whisper text" in page(META, doc)


def test_out_of_order_segments_are_sorted():
    doc = transcript([seg(400, 402, "later"), seg(1, 2, "earlier")])
    body = page(META, doc)
    assert body.index("earlier") < body.index("later")


# --- boundary ---------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "library").mkdir(parents=True)
    monkeypatch.setenv("TAPEDECK_HOME", str(h))
    return h


def install(home, meta, segments):
    d = home / "library" / meta["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta))
    if segments is not None:
        (d / "transcript.json").write_text(json.dumps(transcript(segments)))
    return d


def test_render_one_writes_only_its_page(home):
    install(home, META, [seg(0, 2, "hello")])
    before = sorted(p.name for p in (home / "library" / META["id"]).iterdir())
    render_one(home, META["id"])
    assert sorted(p.name for p in (home / "archive").iterdir()) == [f"{META['id']}.md"]
    assert sorted(p.name for p in (home / "library" / META["id"]).iterdir()) == before


def test_bad_id_shape_is_a_usage_error(home):
    with pytest.raises(Failure) as caught:
        render_one(home, "too-short")
    assert caught.value.code == 2


def test_id_mismatch_is_an_operation_error(home):
    install(home, {**META, "id": "zzzzzzzzzzz"}, [seg(0, 1, "x")])
    d = home / "library" / "zzzzzzzzzzz"
    d.rename(home / "library" / META["id"])
    with pytest.raises(Failure) as caught:
        render_one(home, META["id"])
    assert caught.value.code == 1


def test_malformed_json_reports_the_file(home):
    d = install(home, META, [seg(0, 1, "x")])
    (d / "transcript.json").write_text("{not json")
    with pytest.raises(Failure) as caught:
        render_one(home, META["id"])
    assert "transcript.json" in str(caught.value)


def test_empty_segments_are_rejected(home):
    d = install(home, META, [])
    with pytest.raises(Failure):
        load_transcript(d, META["id"])


def test_meta_needs_a_duration(home):
    d = install(home, {k: v for k, v in META.items() if k != "duration_s"}, [seg(0, 1, "x")])
    with pytest.raises(Failure):
        load_meta(d, META["id"])


def test_render_all_skips_transcriptless_videos_and_reports_failures(home, capsys):
    install(home, META, [seg(0, 1, "ready")])
    install(home, {**META, "id": "waitingonme"}, None)
    broken = install(home, {**META, "id": "brokenmeta0"}, [seg(0, 1, "x")])
    (broken / "meta.json").write_text("{oops")
    assert main(["render-all"]) == 1
    err = capsys.readouterr().err
    assert "waitingonme: skipped" in err and "brokenmeta0" in err
    assert (home / "archive" / f"{META['id']}.md").is_file()
    assert not (home / "archive" / "brokenmeta0.md").exists()


def test_render_all_on_an_empty_library_is_success(home, capsys):
    assert main(["render-all"]) == 0
    assert capsys.readouterr().out == ""


def test_a_failed_write_leaves_no_page_and_no_stray_temp_file(home, monkeypatch):
    install(home, META, [seg(0, 1, "x")])

    def full(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(archive.__main__.os, "replace", full)
    with pytest.raises(Failure):
        render_one(home, META["id"])
    assert list((home / "archive").iterdir()) == []


def test_successful_render_leaves_the_archive_clean(home):
    install(home, META, [seg(0, 1, "x")])
    render_one(home, META["id"])
    assert [p.name for p in (home / "archive").iterdir()] == [f"{META['id']}.md"]


def test_unknown_verb_exits_two(home):
    with pytest.raises(SystemExit) as caught:
        main(["polish"])
    assert caught.value.code == 2
