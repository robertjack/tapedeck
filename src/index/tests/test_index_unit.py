"""Ephemeral unit tests for the index component. Disposable — the durable
acceptance criteria live in system/evals/index/."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from index.pages import PageError, parse

REPO = Path(__file__).resolve().parents[3]


def run(home, *args):
    return subprocess.run(
        [sys.executable, "-m", "index", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "TAPEDECK_HOME": str(home), "PYTHONPATH": str(REPO / "src")},
    )


@pytest.fixture
def home(tmp_path):
    (tmp_path / "archive").mkdir()
    return tmp_path


def write_page(home, video_id, title, body):
    (home / "archive" / f"{video_id}.md").write_text(
        f'---\nid: {video_id}\ntitle: "{title}"\n---\n\n'
        f"## [0:00:00](https://www.youtube.com/watch?v={video_id}&t=0s) Intro\n\n{body}\n"
    )


def test_parse_strips_leading_paragraph_anchor():
    text = (
        "---\nid: aaaaaaaaaaa\ntitle: \"T\"\n---\n\n"
        "## [0:00:05](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=5s) Heading\n\n"
        "[0:00:05](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=5s) Hello world."
    )
    page = parse(text)
    assert page.sections[0].text == "Hello world."


def test_parse_strips_anchor_from_every_paragraph():
    text = (
        "---\nid: aaaaaaaaaaa\ntitle: \"T\"\n---\n\n"
        "## [0:00:00](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=0s) Heading\n\n"
        "[0:00:00](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=0s) First.\n\n"
        "[0:00:10](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=10s) Second."
    )
    page = parse(text)
    assert page.sections[0].text == "First.\n\nSecond."


def test_parse_leaves_unanchored_prose_untouched():
    text = (
        "---\nid: aaaaaaaaaaa\ntitle: \"T\"\n---\n\n"
        "## [0:00:00](https://www.youtube.com/watch?v=aaaaaaaaaaa&t=0s) Heading\n\n"
        "Plain prose [with brackets] here."
    )
    page = parse(text)
    assert page.sections[0].text == "Plain prose [with brackets] here."


def test_parse_rejects_mismatched_filename_id():
    with pytest.raises(PageError):
        parse("---\nid: bbbbbbbbbbb\n---\n", stem="aaaaaaaaaaa")


def test_reindex_then_search_round_trip(home):
    write_page(home, "aaaaaaaaaaa", "Fixture", "Hello regeneration world.")
    r = run(home, "reindex")
    assert r.returncode == 0, r.stderr
    r = run(home, "search", "regeneration", "--json")
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert rows and rows[0]["video_id"] == "aaaaaaaaaaa"
    assert "](https://" not in rows[0]["excerpt"]


def test_search_without_index_is_an_error(home):
    r = run(home, "search", "anything")
    assert r.returncode != 0
    assert "reindex" in (r.stdout + r.stderr).lower()
