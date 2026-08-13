"""Durable evals: ingest expand (SPEC-ingest-002).

Boundary: `python -m ingest expand <url>`, lister via config.toml
[ingest].lister_command. Lister seam pinned here: a shell command run with env
$TAPEDECK_COLLECTION_URL that prints video ids one per line on stdout.
"""

from conftest import run_component

LIST_OK = """#!/bin/sh
echo run >> "$TAPEDECK_HOME/list-count"
printf '%s\\n' dQw4w9WgXcQ plainvide00 dQw4w9WgXcQ another11ch not-an-id
"""
LIST_FAILS = """#!/bin/sh
echo doomed >&2
exit 1
"""

PLAYLIST = "https://www.youtube.com/playlist?list=PLtestfixture01"
CHANNELS = (
    "https://www.youtube.com/@fixturechannel",
    "https://www.youtube.com/@fixturechannel/videos",
    "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
    "https://www.youtube.com/c/FixtureChannel",
    "https://www.youtube.com/user/fixtureuser",
)
SINGLES = (
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "dQw4w9WgXcQ",
    # a watch URL inside a playlist is still one video (SPEC-ingest-002)
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLtestfixture01",
)


def set_lister(home, script_body):
    script = home / "lister.sh"
    script.write_text(script_body)
    (home / "config.toml").write_text(f'[ingest]\nlister_command = "sh {script}"\n')


def expand(home, *args):
    return run_component("ingest", ["expand", *args], home)


def test_single_video_forms_expand_without_the_lister(home):
    set_lister(home, LIST_OK)
    for url in SINGLES:
        r = expand(home, url)
        assert r.returncode == 0, f"{url}: {r.stderr}"
        assert r.stdout.split() == ["dQw4w9WgXcQ"], f"{url}: {r.stdout!r}"
    assert not (home / "list-count").exists(), "lister must not run for single videos"


def test_collection_expands_in_order_deduped_and_filtered(home):
    set_lister(home, LIST_OK)
    r = expand(home, PLAYLIST)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["dQw4w9WgXcQ", "plainvide00", "another11ch"]
    assert (home / "list-count").read_text().count("run") == 1


def test_channel_url_forms_are_collections(home):
    set_lister(home, LIST_OK)
    for url in CHANNELS:
        r = expand(home, url)
        assert r.returncode == 0, f"{url}: {r.stderr}"
        assert "dQw4w9WgXcQ" in r.stdout.split(), f"{url}: {r.stdout!r}"


def test_garbage_exits_2_and_a_failed_lister_exits_1(home):
    set_lister(home, LIST_OK)
    assert expand(home, "https://example.com/nope").returncode == 2
    set_lister(home, LIST_FAILS)
    r = expand(home, PLAYLIST)
    assert r.returncode == 1
    assert r.stdout.strip() == ""


def test_add_refuses_collection_urls(home):
    # ingest downloads exactly one video per invocation; collections go via expand
    set_lister(home, LIST_OK)
    r = run_component("ingest", ["add", PLAYLIST], home)
    assert r.returncode == 2
