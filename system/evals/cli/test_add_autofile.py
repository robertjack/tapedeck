"""Durable evals: the wiki auto-filing epilogue on `add` (Round 3's pinned
interface for `[wiki].auto`).

Boundary: the `tapedeck` executable; fetcher/transcriber/lister seams faked
through config.toml exactly as test_add_collection.py fakes them (its
id-parametric fetcher serves single adds here too), plus a `[wiki]` section
naming a fake maintainer_command — the seam SPEC-wiki-002 defines and
system/evals/wiki exercises directly, reached here through cli's `add` rather
than through `python -m wiki` itself. The maintainer fakes below are
reimplemented rather than imported from system/evals/wiki/wikilib.py so this
suite still runs standalone under `just eval cli`, which only ever puts
system/evals/cli on pytest's collection path.

What Round 3 pins: after each video's ingest -> transcribe -> archive -> index
chain succeeds inside `add`, the cli files that id into the wiki as a
best-effort epilogue, gated by `[wiki].auto` (absent or true files it, false
never touches the wiki at all). A filing that cannot happen — no maintainer
configured, or a maintainer that fails — costs `add` nothing beyond one stderr
note: not its exit code, not the library the pipeline already produced, and
not the collection summary's accounting of what the sweep did.
"""

import json

from conftest import run_cli
from test_add_collection import IDS, PLAYLIST, set_collection_pipeline

# set_collection_pipeline's fetcher is id-parametric, so these two ids (drawn
# from the same fixture playlist) stand in for two unrelated single-video adds.
VIDEO_A = IDS[0]  # "aaaaaaaaaaa"
VIDEO_B = IDS[1]  # "bbbbbbbbbbb"


# --- a maintainer honest enough to pass SPEC-wiki-002's gate -------------------
#
# The gate a real `wiki file` enforces: sources/<id>.md exists and cites <id>;
# index.md links every non-pinned page; log.md gains one well-formed entry;
# CLAUDE.md is untouched; every [[wikilink]] resolves. This maintainer clears
# all five by doing the least a maintainer can do — the same shape as wikilib's
# own FILES_THE_VIDEO, reimplemented here for the reason given above. `t=0s` is
# always in bounds: every fixture video below runs 720s and the fake whisper's
# earliest segment starts at 0.

FILE_BODY = """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Filed from [the fixture](https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID&t=0s).
MD
grep -q "sources/$TAPEDECK_VIDEO_ID.md" index.md ||
  echo "- [$TAPEDECK_VIDEO_ID](sources/$TAPEDECK_VIDEO_ID.md)" >> index.md
{ echo; echo "## [$(date +%Y-%m-%d)] file | $TAPEDECK_VIDEO_ID"; echo;
  echo "Filed by the autofile fixture."; } >> log.md
"""

GOOD = "#!/bin/sh\ncat > /dev/null\n" + FILE_BODY

MUST_NOT_RUN = """#!/bin/sh
touch "$TAPEDECK_HOME/maintainer-ran"
echo "the maintainer was invoked and should not have been" >&2
exit 9
"""

ALWAYS_FAILS = """#!/bin/sh
cat > /dev/null
echo "the fixture maintainer refuses to file $TAPEDECK_VIDEO_ID" >&2
exit 3
"""


def fails_for(video_id):
    """A maintainer that works honestly on every video except one, whose
    filing it refuses outright — the collection sweep's one bad apple."""
    return (
        "#!/bin/sh\ncat > /dev/null\n"
        f'if [ "$TAPEDECK_VIDEO_ID" = "{video_id}" ]; then\n'
        f'  echo "the fixture maintainer refuses to file $TAPEDECK_VIDEO_ID" >&2\n'
        "  exit 3\n"
        "fi\n" + FILE_BODY
    )


def configure_wiki(home, *, auto=None, maintainer=None):
    """Append the `[wiki]` seam (SPEC-wiki-002) to a config.toml a fetcher and
    transcriber seam have already written. config.toml is one file every seam
    shares (SPEC-core-004), so this appends the way test_cli.py's own
    `[ask]` addition does, rather than overwriting what set_collection_pipeline
    wrote — callers that need to change the block between two adds in one test
    call set_collection_pipeline again first to get a clean file to append to."""
    lines = ["\n[wiki]\n"]
    if auto is not None:
        lines.append(f"auto = {'true' if auto else 'false'}\n")
    if maintainer is not None:
        script = home / "maintainer.sh"
        script.write_text(maintainer)
        lines.append(f'maintainer_command = "sh {script}"\n')
    with (home / "config.toml").open("a") as fh:
        fh.write("".join(lines))


def library_artifacts_intact(home, video_id):
    lib = home / "library" / video_id
    media = all((lib / f).is_file() for f in ("video.mp4", "meta.json", "transcript.json"))
    return media and (home / "archive" / f"{video_id}.md").is_file()


# --- `[wiki].auto`: absent reads true, false means hands off entirely --------


def test_auto_toggle_controls_whether_add_files_the_wiki(home):
    """One home, two unrelated videos, the config edited between the two adds:
    the only variable across them is `[wiki].auto`, so the difference in
    outcome is the toggle's doing — and the second half is what keeps this red
    today rather than passing because nothing about the wiki was attempted."""
    set_collection_pipeline(home)
    configure_wiki(home, auto=False, maintainer=MUST_NOT_RUN)
    r_off = run_cli(["add", VIDEO_A], home)
    assert r_off.returncode == 0, r_off.stderr
    assert not (home / "wiki").exists(), "auto = false must never touch the wiki at all"
    assert not (home / "maintainer-ran").exists(), "the maintainer ran despite auto = false"

    set_collection_pipeline(home)  # rebuild the shared config.toml before re-appending
    configure_wiki(home, maintainer=GOOD)  # no `auto` key: the shipped default is true
    r_on = run_cli(["add", VIDEO_B], home)
    assert r_on.returncode == 0, r_on.stderr
    page = home / "wiki" / "sources" / f"{VIDEO_B}.md"
    assert page.is_file(), "an absent `auto` key must read true and file the video"
    assert VIDEO_B in page.read_text()


# --- filing failures cost the wiki, never the pipeline or add's exit code ----


def test_auto_true_with_no_maintainer_command_still_exits_0(home):
    set_collection_pipeline(home)
    configure_wiki(home, auto=True)  # no maintainer_command key at all
    r = run_cli(["add", VIDEO_A], home)
    assert r.returncode == 0, (
        f"an unconfigured maintainer seam must cost only the filing, never add's "
        f"exit code:\n{r.stderr}"
    )
    assert library_artifacts_intact(home, VIDEO_A)
    assert not (home / "wiki" / "sources" / f"{VIDEO_A}.md").exists(), (
        "there is no maintainer to have filed anything"
    )
    assert "maintainer" in r.stderr.lower(), (
        f"the note must name the seam that is missing:\n{r.stderr!r}"
    )


def test_a_failing_maintainer_leaves_add_at_exit_0_with_the_library_intact(home):
    set_collection_pipeline(home)
    configure_wiki(home, maintainer=ALWAYS_FAILS)
    r = run_cli(["add", VIDEO_A], home)
    assert r.returncode == 0, (
        f"a maintainer that fails is a wiki-filing failure, not a pipeline one:\n{r.stderr}"
    )
    assert library_artifacts_intact(home, VIDEO_A)
    results = json.loads(run_cli(["search", "fixture", "--json"], home).stdout)
    assert results and results[0]["video_id"] == VIDEO_A
    assert not (home / "wiki" / "sources" / f"{VIDEO_A}.md").exists(), (
        "a rejected filing must not leave the video looking filed"
    )
    # "wiki" is the anchor, not just the id: today's `add` already prints the id
    # in its ordinary progress lines, so a note that only repeats the id would
    # pass by coincidence rather than by naming what actually failed.
    assert "wiki" in r.stderr.lower() and VIDEO_A in r.stderr, (
        f"the failed filing must be named as a wiki note:\n{r.stderr!r}"
    )


# --- a collection files every video it adds -----------------------------------


def test_collection_add_files_each_added_video(home):
    set_collection_pipeline(home)
    configure_wiki(home, maintainer=GOOD)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    for vid in IDS:
        page = home / "wiki" / "sources" / f"{vid}.md"
        assert page.is_file(), f"{vid} was not filed"
        assert vid in page.read_text()


def test_one_videos_filing_failure_neither_stops_the_sweep_nor_marks_it_failed(home):
    """A control add of the same playlist with no wiki failure at all sets the
    baseline the failing run's summary is measured against — the pinned promise
    is that one bad filing is invisible to `add`'s own accounting, so the two
    summaries must read identically even though their wikis do not."""
    failing = IDS[1]

    baseline = home.parent / "baseline"
    (baseline / "library").mkdir(parents=True)
    (baseline / "config.toml").write_text("# fixture config\n")
    set_collection_pipeline(baseline)
    configure_wiki(baseline, maintainer=GOOD)
    control = run_cli(["add", PLAYLIST], baseline)
    assert control.returncode == 0, control.stderr

    set_collection_pipeline(home)
    configure_wiki(home, maintainer=fails_for(failing))
    r = run_cli(["add", PLAYLIST], home)

    assert r.returncode == 0, (
        f"a wiki filing failure must never flip add's own exit code:\n{r.stderr}"
    )
    for vid in IDS:
        assert library_artifacts_intact(home, vid), (
            f"{vid}'s pipeline output must be untouched by the wiki failure"
        )
    assert (home / "wiki" / "sources" / f"{IDS[0]}.md").is_file()
    assert (home / "wiki" / "sources" / f"{IDS[2]}.md").is_file()
    assert not (home / "wiki" / "sources" / f"{failing}.md").exists()
    # "wiki" anchors this as a filing note, not a coincidental match against the
    # id's ordinary presence in add's own fetch/transcribe progress lines.
    assert "wiki" in r.stderr.lower() and failing in r.stderr, (
        f"the one filing failure is reported as a wiki note:\n{r.stderr!r}"
    )

    assert r.stdout == control.stdout, (
        "one video's filing failure must not appear in the collection summary "
        f"at all:\n{r.stdout!r}\nvs a run where nothing about the wiki failed:\n"
        f"{control.stdout!r}"
    )
