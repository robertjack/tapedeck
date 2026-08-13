"""Durable evals: ask (SPEC-ask-001, SPEC-ask-002, contracts/ask-citations.md).

Boundary: `python -m ask run "<question>" [-k N] [--fast]`, library via
$TAPEDECK_HOME. Default = librarian mode (conftest.set_librarian pins the seam);
`--fast` = strict retrieval pipeline (conftest.set_answerer). Fast-mode retrieval
uses the index component's database; fixtures build it via `python -m index reindex`.
"""

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
    (610, "Wrap Up", "Thanks for watching, goodbye."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]

LIBRARIAN_OK = """#!/bin/sh
pwd > "$TAPEDECK_HOME/librarian-cwd"
cat > "$TAPEDECK_HOME/librarian-prompt"
cat <<'EOF'
The library is about building things [see intro](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s).
EOF
"""
LIBRARIAN_FABRICATES = """#!/bin/sh
cat > /dev/null
printf 'Confident claim [source](https://www.youtube.com/watch?v=nosuchvid00&t=10s).\\n'
"""
LIBRARIAN_OVERTIME = """#!/bin/sh
cat > /dev/null
printf 'Late claim [source](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9999s).\\n'
"""
LIBRARIAN_UNCITED = """#!/bin/sh
cat > /dev/null
printf 'A confident answer with no citations at all.\\n'
"""

ANSWER_OK = """#!/bin/sh
cat > "$TAPEDECK_HOME/prompt-seen"
printf 'The library says regeneration beats maintenance [1].\\n'
"""
ANSWER_INVENTS = """#!/bin/sh
cat > /dev/null
printf 'Something confident [9].\\n'
"""


def ask(home, *args):
    return run_component("ask", ["run", *args], home)


def librarian_home(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    set_librarian(home, LIBRARIAN_OK)


def indexed_home(home):
    write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    write_archive_page(home, PLAIN_META, BREAD_SECTIONS)
    r = run_component("index", ["reindex"], home)
    assert r.returncode == 0, r.stderr


# --- librarian mode (default) ---


def test_librarian_answers_with_verified_citations(home):
    librarian_home(home)
    r = ask(home, "what is this library about")
    assert r.returncode == 0, r.stderr
    assert "building things" in r.stdout
    assert "watch?v=dQw4w9WgXcQ&t=95s" in r.stdout
    assert (home / "librarian-cwd").read_text().strip() == str(home)
    assert "what is this library about" in (home / "librarian-prompt").read_text()


def test_fabricated_video_citation_rejected(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    set_librarian(home, LIBRARIAN_FABRICATES)
    r = ask(home, "anything")
    assert r.returncode == 1
    assert "citation" in r.stderr.lower() or "source" in r.stderr.lower()


def test_timestamp_beyond_duration_rejected(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    set_librarian(home, LIBRARIAN_OVERTIME)
    r = ask(home, "anything")
    assert r.returncode == 1


def test_uncited_answer_rejected(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    set_librarian(home, LIBRARIAN_UNCITED)
    r = ask(home, "anything")
    assert r.returncode == 1


def test_empty_library_refuses_without_invoking_librarian(home):
    set_librarian(home, LIBRARIAN_OK)
    r = ask(home, "anything at all")
    assert r.returncode == 1
    assert "no sources in the library" in r.stderr
    assert not (home / "librarian-cwd").exists()


def test_missing_brief_is_a_config_error(home):
    librarian_home(home)
    (home / "CLAUDE.md").unlink()
    r = ask(home, "anything")
    assert r.returncode == 2
    assert "brief" in r.stderr.lower() or "claude.md" in r.stderr.lower()


def test_missing_librarian_config_is_an_error(home):
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    (home / "config.toml").write_text("# no ask section\n")
    (home / "CLAUDE.md").write_text("# brief\n")
    r = ask(home, "anything")
    assert r.returncode == 2
    assert "librarian" in r.stderr.lower()


# --- fast mode (--fast): the strict retrieval pipeline ---


def test_fast_answer_carries_tapedeck_assembled_sources(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "what is the core idea", "-k", "3", "--fast")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "regeneration beats maintenance [1]" in out
    assert "Sources:" in out
    assert "Test Video: Building Things" in out
    assert "0:01:35" in out
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s" in out
    prompt = (home / "prompt-seen").read_text()
    assert "what is the core idea" in prompt
    assert "The core idea is regeneration over maintenance." in prompt
    assert "not in the library" in prompt
    assert "[1]" in prompt


def test_fast_no_retrieval_means_answerer_never_runs(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "xylophone quantum blockchain", "--fast")
    assert r.returncode == 1
    assert "no sources in the library" in r.stderr
    assert not (home / "prompt-seen").exists()


def test_fast_invented_citation_is_rejected(home):
    indexed_home(home)
    set_answerer(home, ANSWER_INVENTS)
    r = ask(home, "what is the core idea", "-k", "2", "--fast")
    assert r.returncode == 1
    assert "citation" in r.stderr.lower() or "source" in r.stderr.lower()


def test_fast_k_bounds_the_source_list(home):
    indexed_home(home)
    set_answerer(home, ANSWER_OK)
    r = ask(home, "content about sourdough proofing", "-k", "1", "--fast")
    assert r.returncode == 0, r.stderr
    assert "[2]" not in r.stdout


def test_fast_failed_answerer_is_a_clean_error(home):
    indexed_home(home)
    set_answerer(home, "#!/bin/sh\ncat > /dev/null\nexit 1\n")
    r = ask(home, "what is the core idea", "--fast")
    assert r.returncode == 1
