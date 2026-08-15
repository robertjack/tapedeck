"""Ephemeral unit tests for ask — disposable, unlike system/evals/ask.

These poke at the seams between the pieces the durable evals only see through the
process boundary: how a citation is read out of prose, that librarian mode and the
`verify` verb are literally one reading (SPEC-ask-005), and how a question becomes
an fts5 MATCH.
"""

from __future__ import annotations

import io
import json

import pytest

from ask import citations
from ask.__main__ import Failure, main, scope_for, verify
from ask.library import Library

VID = "dQw4w9WgXcQ"
OTHER = "plainvide00"


def stock(home, video_id=VID, duration=720):
    d = home / "library" / video_id
    d.mkdir(parents=True)
    meta = {"id": video_id, "title": "T", "channel": "C", "duration_s": duration}
    (d / "meta.json").write_text(json.dumps(meta))
    return Library(home)


# --- reading a citation out of a sentence (contracts/ask-citations.md) ---


@pytest.mark.parametrize(
    "text, video_id, seconds",
    [
        (f"see [x](https://www.youtube.com/watch?v={VID}&t=95s).", VID, 95),
        (f"bare https://www.youtube.com/watch?v={VID}.", VID, None),
        (f"comma https://www.youtube.com/watch?v={VID}&t=95s, then", VID, 95),
        (f"quoted \"https://www.youtube.com/watch?v={VID}&t=95s\"", VID, 95),
        (f"hms https://www.youtube.com/watch?v={VID}&t=1h2m3s!", VID, 3723),
        (f"short https://youtu.be/{VID}?t=42", VID, 42),
    ],
)
def test_punctuation_is_prose_not_url(text, video_id, seconds):
    (cite,) = citations.deep_links(text)
    assert cite.video_id == video_id
    assert cite.seconds == seconds
    assert not cite.url.endswith((".", ",", '"', "!"))


def test_an_unreadable_offset_is_a_failed_citation_not_a_waived_one(tmp_path):
    """A `t=` the parser gives up on must not read as 'claims no moment'."""
    library = stock(tmp_path)
    (cite,) = citations.deep_links(f"https://www.youtube.com/watch?v={VID}&t=half-past")
    assert cite.stated and cite.seconds is None
    assert citations.unverified([cite], library)


def test_no_link_means_no_citation():
    assert citations.deep_links("plain prose, no links, https://example.com/x") == []


# --- the bounds check ---


def test_in_bounds_moment_verifies(tmp_path):
    library = stock(tmp_path)
    assert citations.audit(f"[a](https://www.youtube.com/watch?v={VID}&t=95s).", library) == []


def test_moment_past_the_end_is_a_fabrication(tmp_path):
    library = stock(tmp_path)
    problems = citations.audit(f"https://www.youtube.com/watch?v={VID}&t=9999s.", library)
    assert len(problems) == 1
    assert "9999" in problems[0]


def test_unknown_duration_bounds_nothing_but_existence_still_holds(tmp_path):
    library = stock(tmp_path, duration=0)  # ingest's "the source withheld it"
    assert citations.audit(f"https://www.youtube.com/watch?v={VID}&t=9999s.", library) == []
    absent = citations.audit("https://www.youtube.com/watch?v=nosuchvid00&t=1s.", library)
    assert absent and "nosuchvid00" in absent[0]


def test_unreadable_meta_bounds_nothing_either(tmp_path):
    library = stock(tmp_path)
    (tmp_path / "library" / VID / "meta.json").write_text("{ not json")
    assert Library(tmp_path).holds(VID)
    assert citations.audit(f"https://www.youtube.com/watch?v={VID}&t=9999s.", library) == []


def test_every_violation_is_reported_not_just_the_first(tmp_path):
    library = stock(tmp_path)
    text = (
        f"https://www.youtube.com/watch?v={VID}&t=9999s and "
        "https://www.youtube.com/watch?v=nosuchvid00&t=1s and "
        f"https://www.youtube.com/watch?v={VID}&t=95s"
    )
    assert len(citations.audit(text, library)) == 2


# --- one reading, two doors (SPEC-ask-005) ---


def test_require_citation_is_the_only_difference_between_the_doors(tmp_path):
    """Librarian mode demands a link; verify does so only when asked. Everything
    else about the verdict must be the same call, not a second implementation."""
    library = stock(tmp_path)
    uncited = "A confident answer with no citations at all."
    assert citations.audit(uncited, library, require_citation=True) == [citations.UNCITED]
    assert citations.audit(uncited, library) == []


@pytest.mark.parametrize(
    "text",
    [
        f"It happens right [here](https://www.youtube.com/watch?v={VID}&t=95s).",
        f"The build is covered at https://www.youtube.com/watch?v={VID}.",
        f"See https://www.youtube.com/watch?v={VID}&t=95s, which says so.",
        f"It is settled at https://www.youtube.com/watch?v={VID}&t=9999s.",
        "Covered in [nothing](https://www.youtube.com/watch?v=nosuchvid00&t=95s).",
    ],
)
def test_both_doors_reach_the_same_verdict(tmp_path, monkeypatch, capsys, text):
    """The verb's exit code must follow `audit` exactly — the claim the durable
    evals check from outside, checked here against the function itself."""
    library = stock(tmp_path)
    expected = bool(citations.audit(text, library, require_citation=True))
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    if expected:
        with pytest.raises(Failure):
            verify(library, None, True)
    else:
        assert verify(library, None, True) == 0
    capsys.readouterr()


# --- scope ---


def test_scope_rejects_another_library_video(tmp_path):
    stock(tmp_path)
    library = stock(tmp_path, OTHER)
    text = f"[bread](https://www.youtube.com/watch?v={OTHER}&t=10s)"
    assert citations.audit(text, library) == []  # in the library
    problems = citations.audit(text, library, scope=VID)  # but not in scope
    assert problems and OTHER in problems[0]


def test_unknown_scope_id_is_a_usage_error(tmp_path):
    library = stock(tmp_path)
    with pytest.raises(Failure) as caught:
        scope_for(library, "nosuchvid00")
    assert caught.value.code == 2
    assert "nosuchvid00" in str(caught.value)


def test_a_scope_check_costs_one_path_lookup(tmp_path, monkeypatch):
    """SPEC-ask-003: settled by asking whether library/<id> is there, never by
    enumerating a library that grows without bound."""
    library = stock(tmp_path)
    monkeypatch.setattr(
        Library, "stocked", lambda self: pytest.fail("scoping must not scan the library")
    )
    assert scope_for(library, VID) == VID
    assert scope_for(library, None) is None


# --- verify runs nothing and writes nothing ---


def test_verify_touches_no_seam_and_no_file(tmp_path, monkeypatch):
    library = stock(tmp_path)
    monkeypatch.setattr("ask.seams.run", lambda *a, **k: pytest.fail("no seam may run"))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr("sys.stdin", io.StringIO("no links here"))
    assert verify(library, None, False) == 0
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_verify_exit_codes_through_main(tmp_path, monkeypatch, capsys):
    stock(tmp_path)
    monkeypatch.setenv("TAPEDECK_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(f"ok https://www.youtube.com/watch?v={VID}&t=1s"))
    assert main(["verify"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("https://www.youtube.com/watch?v=nosuchvid00"))
    assert main(["verify"]) == 1
    assert "nosuchvid00" in capsys.readouterr().err
    assert main(["verify", "--video", "nosuchvid00"]) == 2


# --- fast-mode prompt and query building ---


def test_prompt_carries_the_grounding_rules_and_the_markers():
    source = retrieval_source()
    text = citations.prompt("what is the core idea", [source])
    assert "not in the library" in text
    assert "[1]" in text
    assert "what is the core idea" in text
    assert source.text in text


def test_sources_block_numbers_every_retrieved_chunk():
    block = citations.sources_block([retrieval_source(), retrieval_source(start=300)])
    assert "[1]" in block and "[2]" in block
    assert "0:01:35" in block and "0:05:00" in block


def test_invented_markers_are_the_ones_no_source_carries():
    assert citations.invented("a [1] b [9]", 3) == [9]
    assert citations.invented("a [1] b [3]", 3) == []


def retrieval_source(start=95):
    from ask.retrieve import Source

    return Source(VID, "Test Video", "Fixture Channel", "The Core Idea", start, "Body text.")


@pytest.mark.parametrize(
    "question, expected",
    [
        ("what is the core idea", ["core", "idea"]),
        ("what is it", ["what", "is", "it"]),  # all grammar: keep it rather than nothing
        ('"core idea" please', ["core idea", "please"]),
        ("C++ and ???", ["C++"]),
    ],
)
def test_question_words_survive_and_grammar_drops(question, expected):
    from ask.retrieve import terms

    assert terms(question) == expected


def test_match_expression_ors_phrases_and_cannot_be_syntax():
    from ask.retrieve import match_expression

    assert match_expression("core idea") == '"core" OR "idea"'
    assert match_expression('a "quoted" one') == '"quoted" OR "one"'
