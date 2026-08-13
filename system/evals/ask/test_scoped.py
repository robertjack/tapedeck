"""Durable evals: ask --video scoping (SPEC-ask-003).

Boundary: `python -m ask run "<question>" [--video <id>] [-k N] [--fast]`.
"""

import json

from conftest import (
    CHAPTERED_META,
    PLAIN_META,
    add_video,
    run_component,
    set_answerer,
    set_librarian,
    write_archive_page,
)

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]

ANSWER_OK = """#!/bin/sh
cat > "$TAPEDECK_HOME/prompt-seen"
printf 'Scoped fast answer [1].\\n'
"""
LIBRARIAN_IN_SCOPE = """#!/bin/sh
cat > "$TAPEDECK_HOME/librarian-prompt"
printf 'Scoped answer [see](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s).\\n'
"""
LIBRARIAN_OUT_OF_SCOPE = """#!/bin/sh
cat > /dev/null
printf 'Answer citing a real but out-of-scope video [see](https://www.youtube.com/watch?v=plainvide00&t=10s).\\n'
"""


def ask(home, *args):
    return run_component("ask", ["run", *args], home)


def indexed_home(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    add_video(home, PLAIN_META, [{"start": 2.0, "end": 6.0, "text": "Sourdough."}])
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr


def test_fast_scoped_retrieval_stays_in_the_video(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "the core idea", "--fast", "--video", CHAPTERED_META["id"])
    assert r.returncode == 0, r.stderr
    assert CHAPTERED_META["id"] in r.stdout
    assert PLAIN_META["id"] not in r.stdout, "Sources must cite only the scoped video"


def test_fast_scope_with_no_matches_refuses_without_invocation(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    # sourdough lives only in the other video; scoped retrieval must come up empty
    r = ask(home, "sourdough starters", "--fast", "--video", CHAPTERED_META["id"])
    assert r.returncode == 1
    assert not (home / "prompt-seen").exists(), "empty scoped retrieval must not invoke"


def test_unknown_scope_id_exits_2_before_any_invocation(home):
    indexed_home(home)
    set_librarian(home, LIBRARIAN_IN_SCOPE)
    r = ask(home, "anything", "--video", "nosuchvid00")
    assert r.returncode == 2
    assert not (home / "librarian-prompt").exists()


def test_librarian_scope_is_stated_and_enforced(home):
    indexed_home(home)
    set_librarian(home, LIBRARIAN_IN_SCOPE)
    r = ask(home, "what is the core idea", "--video", CHAPTERED_META["id"])
    assert r.returncode == 0, r.stderr
    prompt = (home / "librarian-prompt").read_text()
    assert CHAPTERED_META["id"] in prompt, "the librarian must be told the scope"
    set_librarian(home, LIBRARIAN_OUT_OF_SCOPE)
    r = ask(home, "what is the core idea", "--video", CHAPTERED_META["id"])
    assert r.returncode == 1, "a citation outside the scope is a fabrication"
