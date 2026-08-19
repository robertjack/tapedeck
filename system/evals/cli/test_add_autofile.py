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
never touches the wiki at all). A filing that cannot happen costs `add`
nothing: not its exit code, not the library the pipeline already produced, and
not the collection summary's accounting of what the sweep did.

Amended for SPEC-cli-011 (the detached epilogue): outcomes are settled by
polling rather than read off `add`'s return, because the filings may finish
after `add` does, and a failure after hand-off is asserted through what it
durably leaves (an unfiled video) rather than through a stderr note on a
terminal the spec says has moved on. The pre-hand-off notes — `auto = false`,
an unconfigured maintainer seam — remain synchronous and stay pinned as such.
"""

import json
import time

from conftest import TIMEOUT, run_cli
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
touch "$TAPEDECK_HOME/attempted-$TAPEDECK_VIDEO_ID"
echo "the fixture maintainer refuses to file $TAPEDECK_VIDEO_ID" >&2
exit 3
"""


def fails_for(video_id):
    """A maintainer that works honestly on every video except one, whose
    filing it refuses outright — the collection sweep's one bad apple. The
    refusal leaves a marker in the home, the only durable proof the filing was
    reached: a rejected run makes no commit and no chronology entry."""
    return (
        "#!/bin/sh\ncat > /dev/null\n"
        f'if [ "$TAPEDECK_VIDEO_ID" = "{video_id}" ]; then\n'
        f'  touch "$TAPEDECK_HOME/attempted-$TAPEDECK_VIDEO_ID"\n'
        f'  echo "the fixture maintainer refuses to file $TAPEDECK_VIDEO_ID" >&2\n'
        "  exit 3\n"
        "fi\n" + FILE_BODY
    )


def settled(condition, message):
    """Poll until `condition()` holds: the epilogue's worker is, by
    specification, nobody's child to wait on (SPEC-cli-011)."""
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, message
        time.sleep(0.2)


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
    the only variable across them is `[wiki].auto`. Amended for the public
    era (SPEC-cli-009): the wiki spends only when asked, so an ABSENT key —
    every fresh install, every stranger with claude on PATH — never touches
    the wiki, and `auto = true` is the deliberate line that turns it on."""
    set_collection_pipeline(home)
    configure_wiki(home, maintainer=MUST_NOT_RUN)  # no `auto` key at all
    r_off = run_cli(["add", VIDEO_A], home)
    assert r_off.returncode == 0, r_off.stderr

    set_collection_pipeline(home)  # rebuild the shared config.toml before re-appending
    configure_wiki(home, auto=True, maintainer=GOOD)  # the deliberate opt-in
    r_on = run_cli(["add", VIDEO_B], home)
    assert r_on.returncode == 0, r_on.stderr
    page = home / "wiki" / "sources" / f"{VIDEO_B}.md"
    settled(page.is_file, "auto = true is the opt-in and must file the video")
    assert VIDEO_B in page.read_text()

    # Only now is the negative deterministic: B's filing landed, and any worker
    # A's add had wrongly spawned ran serially ahead of B's behind the wiki
    # lock — so A's absence of traces is proof, not a race won by asserting
    # before a detached worker got started.
    assert not (home / "maintainer-ran").exists(), (
        "an absent auto key reads false: a first add must never spend the "
        "user's agent budget unasked"
    )
    assert not (home / "wiki" / "sources" / f"{VIDEO_A}.md").exists(), (
        f"{VIDEO_A} was filed despite auto being absent"
    )


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
    settled(
        lambda: (home / f"attempted-{VIDEO_A}").exists(),
        "the filing was never even attempted",
    )
    assert not (home / "wiki" / "sources" / f"{VIDEO_A}.md").exists(), (
        "a rejected filing must not leave the video looking filed"
    )
    # The one word add's stderr must still carry: the epilogue exists ("wiki" —
    # today as the failure note, under SPEC-cli-011 as the hand-off line).
    assert "wiki" in r.stderr.lower(), (
        f"add's stderr must acknowledge the wiki epilogue:\n{r.stderr!r}"
    )


# --- a collection files every video it adds -----------------------------------


def test_collection_add_files_each_added_video(home):
    set_collection_pipeline(home)
    configure_wiki(home, maintainer=GOOD)
    r = run_cli(["add", PLAYLIST], home)
    assert r.returncode == 0, r.stderr
    pages = {vid: home / "wiki" / "sources" / f"{vid}.md" for vid in IDS}
    settled(
        lambda: all(p.is_file() for p in pages.values()),
        f"unfiled: {[v for v, p in pages.items() if not p.is_file()]}",
    )
    for vid, page in pages.items():
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
    survivors = [home / "wiki" / "sources" / f"{IDS[0]}.md",
                 home / "wiki" / "sources" / f"{IDS[2]}.md"]
    settled(
        lambda: all(p.is_file() for p in survivors)
        and (home / f"attempted-{failing}").exists(),
        "the sweep's other filings (or the failing attempt) never landed",
    )
    assert not (home / "wiki" / "sources" / f"{failing}.md").exists()
    assert "wiki" in r.stderr.lower(), (
        f"add's stderr must acknowledge the wiki epilogue:\n{r.stderr!r}"
    )

    assert r.stdout == control.stdout, (
        "one video's filing failure must not appear in the collection summary "
        f"at all:\n{r.stdout!r}\nvs a run where nothing about the wiki failed:\n"
        f"{control.stdout!r}"
    )
