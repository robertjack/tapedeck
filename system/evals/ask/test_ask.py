"""Durable evals: ask (SPEC-ask-001, SPEC-ask-002, contracts/ask-citations.md).

Boundary: `python -m ask run "<question>" [-k N]`, library via $TAPEDECK_HOME,
answerer via config.toml [ask] (see conftest.set_answerer). Retrieval uses the
index component's database; fixtures build it via `python -m index reindex`.
"""

from conftest import (
    CHAPTERED_META,
    PLAIN_META,
    run_component,
    set_answerer,
    write_archive_page,
)

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
    (610, "Wrap Up", "Thanks for watching, goodbye."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]

ANSWER_OK = """#!/bin/sh
cat > "$TAPEDECK_HOME/prompt-seen"
printf 'The library says regeneration beats maintenance [1].\\n'
"""
ANSWER_INVENTS = """#!/bin/sh
cat > /dev/null
printf 'Something confident [9].\\n'
"""
ANSWER_FAILS = """#!/bin/sh
cat > /dev/null
exit 1
"""


def indexed_home(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr


def ask(home, *args):
    return run_component("ask", ["run", *args], home)


def test_answer_carries_tapedeck_assembled_sources(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "what is the core idea", "-k", "3")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "regeneration beats maintenance [1]" in out
    assert "Sources:" in out
    assert "Test Video: Building Things" in out
    assert "0:01:35" in out
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in out
    # SPEC-ask-002: the prompt is part of the testable surface
    prompt = (home / "prompt-seen").read_text()
    assert "what is the core idea" in prompt
    assert "The core idea is regeneration over maintenance." in prompt
    assert "not in the library" in prompt  # the insufficient-sources instruction
    assert "[1]" in prompt                 # sources are numbered for citing


def test_no_retrieval_means_answerer_never_runs(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "xylophone quantum blockchain")
    assert r.returncode == 1
    assert "no sources in the library" in r.stderr
    assert not (home / "prompt-seen").exists()


def test_invented_citation_is_rejected(home):
    indexed_home(home)
    set_answerer(home, ANSWER_INVENTS)
    r = ask(home, "what is the core idea", "-k", "2")
    assert r.returncode == 1
    assert "citation" in r.stderr.lower() or "source" in r.stderr.lower()


def test_k_bounds_the_source_list(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "content about sourdough proofing", "-k", "1")
    assert r.returncode == 0, r.stderr
    assert "[2]" not in r.stdout


def test_failed_answerer_is_a_clean_error(home):
    indexed_home(home)
    set_answerer(home, ANSWER_FAILS)
    r = ask(home, "what is the core idea")
    assert r.returncode == 1


def test_missing_answerer_config_is_an_error(home):
    indexed_home(home)
    (home / "config.toml").write_text("# no ask section\n")
    r = ask(home, "what is the core idea")
    assert r.returncode == 2
    assert "answerer" in r.stderr.lower()
