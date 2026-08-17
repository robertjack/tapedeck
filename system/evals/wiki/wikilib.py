"""Fixtures shared by the wiki suites (SPEC-wiki-001 through SPEC-wiki-005).

Deliberately not a `conftest.py`: `conftest` is the name every suite imports the
shared harness by, and a second module of that name on the path would shadow it.

Two seams are faked here. The maintainer is faked through config.toml
(conftest.set_maintainer) — a shell script standing in for the agent, so what the
acceptance gate does with a wiki is decided by fixtures rather than by a model.
ask is faked through `$TAPEDECK_ASK_CMD`, the override the harness documents for
every component boundary: wiki consumes ask's published verification verb
(SPEC-ask-005) rather than re-reading citations itself (LESSON-0003), so these
suites pin what wiki does with a verdict and system/evals/ask pins how ask
reaches one.

The maintainer fakes are assembled from one honest body plus a single line that
breaks one rule, so each gate eval names the one thing it changed.
"""

import re
import subprocess

from conftest import (
    CHAPTERED_META,
    PLAIN_META,
    TIMEOUT,
    add_video,
    run_component,
    set_maintainer,
    write_archive_page,
)

FILED = CHAPTERED_META["id"]  # the video the fixtures file first
NEXT = PLAIN_META["id"]       # the one every later operation tries to file

CH_SECTIONS = [
    (0, "Intro", "Welcome to the fixture show."),
    (95, "The Core Idea", "The core idea is regeneration over maintenance."),
]
BREAD_SECTIONS = [
    (0, "Part 1", "Block one content about sourdough starters."),
    (300, "Part 2", "Block two content about proofing times."),
]

# The pinned chronology entry: '## [YYYY-MM-DD] <op> | <subject>'.
ENTRY = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] \S+ \| .+$", re.MULTILINE)

# --- the ask fake -----------------------------------------------------------

ASK_VERIFIES = """#!/bin/sh
{ echo "argv: $*"; cat; echo; echo "=== end of call ==="; } >> "$TAPEDECK_HOME/ask-calls"
"""
ASK_REPORTS_A_FABRICATION = """#!/bin/sh
cat > /dev/null
echo "unverifiable citation: t=9999s is past the end of the video" >&2
exit 1
"""


def set_ask(monkeypatch, home, script_body=ASK_VERIFIES):
    """Point wiki's citation check at a fake ask. Interface pinned here: wiki
    invokes ask as `$TAPEDECK_ASK_CMD` when set, else `<current python> -m ask`,
    with one page's text on stdin; exit 0 means every deep link in that text
    verified, nonzero means it did not and the violations are on stderr."""
    script = home / "fake-ask.sh"
    script.write_text(script_body)
    monkeypatch.setenv("TAPEDECK_ASK_CMD", f"sh {script}")


def ask_calls(home):
    """The fake's record, one `(argv, text)` pair per invocation. Read per call
    rather than as one blob: the gate may ask ask more than one question about a
    page, and an assertion about the whole file would pin which."""
    raw = (home / "ask-calls").read_text()
    calls = []
    for chunk in raw.split("=== end of call ===\n"):
        if not chunk.strip():
            continue
        argv, _, text = chunk.partition("\n")
        calls.append((argv, text))
    return calls


# --- the maintainer fakes ---------------------------------------------------

SH = """#!/bin/sh
cat > /dev/null
"""

# Writes the page the filed state is made of, a note it links to, and the catalog
# lines for both — the least a maintainer can do and still be accepted.
FILES_THE_VIDEO = """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Filed from [the moment it matters](https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID&t=95s).
Belongs with [[regeneration|the idea behind it]].
MD
cat > "notes/regeneration.md" <<MD
# Regeneration

Traced back to [[$TAPEDECK_VIDEO_ID]].
MD
grep -q "sources/$TAPEDECK_VIDEO_ID.md" index.md ||
  echo "- [$TAPEDECK_VIDEO_ID](sources/$TAPEDECK_VIDEO_ID.md)" >> index.md
grep -q "notes/regeneration.md" index.md ||
  echo "- [Regeneration](notes/regeneration.md)" >> index.md
"""

LOGS_IT = """
{ echo; echo "## [$(date +%Y-%m-%d)] file | $TAPEDECK_VIDEO_ID"; echo;
  echo "Filed the video and linked it to regeneration."; } >> log.md
"""

GOOD = SH + FILES_THE_VIDEO + LOGS_IT

# Records the seam it was handed before doing the same honest work. Writing the
# record to $TAPEDECK_HOME is itself the proof that variable reached it.
RECORDS_THE_SEAM = (
    """#!/bin/sh
{ pwd
  echo "wiki=$TAPEDECK_WIKI"
  echo "id=$TAPEDECK_VIDEO_ID"
  echo "page=$TAPEDECK_ARCHIVE_PAGE"
  echo "--- task ---"
  cat
} > "$TAPEDECK_HOME/maintainer-log"
"""
    + FILES_THE_VIDEO
    + LOGS_IT
)

DOES_NOTHING = SH

FAILS = SH + """
echo "half a thought" > "notes/half.md"
exit 3
"""

MUST_NOT_RUN = """#!/bin/sh
touch "$TAPEDECK_HOME/maintainer-ran"
echo "the maintainer was invoked and should not have been" >&2
exit 9
"""

LINKS_TO_NOTHING = GOOD + """
echo "Compare with [[nonexistent-page]]." >> "sources/$TAPEDECK_VIDEO_ID.md"
"""

LINKS_IN_THE_WRONG_CASE = GOOD + """
echo "See also [[Regeneration]]." >> "sources/$TAPEDECK_VIDEO_ID.md"
"""

LEAVES_A_PAGE_OUT_OF_THE_INDEX = GOOD + """
echo "# Stray" > "notes/stray.md"
"""

REWRITES_THE_LOG = SH + FILES_THE_VIDEO + """
echo "# Wiki log" > log.md
""" + LOGS_IT

LOGS_NOTHING_WELL_FORMED = SH + FILES_THE_VIDEO + """
echo "filed another one" >> log.md
"""

EDITS_THE_BRIEF = GOOD + """
echo "- also: rename pages freely" >> CLAUDE.md
"""

CITES_ANOTHER_VIDEO_ONLY = SH + """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Same ground as [the other one](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s).
MD
grep -q "sources/$TAPEDECK_VIDEO_ID.md" index.md ||
  echo "- [$TAPEDECK_VIDEO_ID](sources/$TAPEDECK_VIDEO_ID.md)" >> index.md
""" + LOGS_IT

BREAKS_TWO_RULES = LINKS_TO_NOTHING + """
echo "- also: rename pages freely" >> CLAUDE.md
"""

# SPEC-wiki-008: the maintainer's whole half of a filing and nothing else. It
# writes the pages and stops — no catalog line, no chronology entry — because the
# task no longer asks for either and the bookkeeping is tapedeck's. `notes/
# proofing.md` is new to this wiki (the fixture filing wrote `regeneration`), so
# whether it reaches the catalog is a question only tapedeck can answer.
WRITES_THE_PAGES = """
cat > "sources/$TAPEDECK_VIDEO_ID.md" <<MD
# $TAPEDECK_VIDEO_ID

Filed from [the moment it matters](https://www.youtube.com/watch?v=$TAPEDECK_VIDEO_ID&t=95s).
Belongs with [[proofing|the idea behind it]].
MD
cat > "notes/proofing.md" <<MD
# Proofing times

Picked up from [[$TAPEDECK_VIDEO_ID]].
MD
"""

FILES_ONLY_THE_PAGES = SH + WRITES_THE_PAGES

NEW_NOTE = "notes/proofing.md"
NEW_NOTE_HEADING = "Proofing times"

# The same honest work, with the task it was handed kept for inspection. What
# tapedeck says to the maintainer is as much a pinned surface as what it does to
# the wiki afterwards — SPEC-wiki-008 removed instructions from it and
# SPEC-wiki-009 adds knowledge to it, and both are only observable here.
RECORDS_THE_TASK = '#!/bin/sh\ncat > "$TAPEDECK_HOME/task"\n' + WRITES_THE_PAGES


def task_given(home):
    """The task text the maintainer was handed on stdin."""
    return (home / "task").read_text()


# --- driving the boundary ---------------------------------------------------


def wiki_file(home, video_id):
    return run_component("wiki", ["file", video_id], home)


def wiki_sync(home, *flags):
    return run_component("wiki", ["sync", *flags], home)


def wiki_rebuild(home, *flags):
    return run_component("wiki", ["rebuild", *flags], home)


def stocked(home, pages=(FILED, NEXT)):
    """The library `wiki file` reads: two videos, and by default the archive page
    for each. `pages` narrows that — a video ingest holds but archive never
    rendered is a case of its own."""
    add_video(home, CHAPTERED_META, [{"start": 0.0, "end": 4.0, "text": "Welcome."}])
    add_video(home, PLAIN_META, [{"start": 2.0, "end": 6.0, "text": "Sourdough."}])
    if FILED in pages:
        write_archive_page(home, CHAPTERED_META, CH_SECTIONS)
    if NEXT in pages:
        write_archive_page(home, PLAIN_META, BREAD_SECTIONS)


def git(wiki, *args):
    return subprocess.run(
        ["git", *args], cwd=wiki, capture_output=True, text=True, timeout=TIMEOUT
    )


def subjects(wiki):
    """Commit subjects, newest first — the wiki's history as the user reads it."""
    r = git(wiki, "log", "--format=%s")
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def snapshot(wiki):
    """Every byte of the wiki except its git internals. Equality with a later
    snapshot is what "restored" means: a reset that misses an untracked page the
    maintainer left behind is not a restore."""
    return {
        str(p.relative_to(wiki)): p.read_bytes()
        for p in sorted(wiki.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(wiki).parts
    }


def filed(home, monkeypatch):
    """A wiki with one video already filed — the pre-run state later operations
    are measured against. Returns the wiki directory."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, GOOD)
    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"the fixture wiki must file cleanly:\n{r.stdout}\n{r.stderr}"
    return home / "wiki"


def accepted(home, monkeypatch, maintainer, ask=ASK_VERIFIES):
    """File a second video with a maintainer that does its own half of the work
    and leaves tapedeck's half undone (SPEC-wiki-008), and hold the run to what an
    acceptance promises: exit 0, and exactly one new commit. Returns `(run, wiki)`
    so the caller can read what tapedeck made of the result."""
    wiki = filed(home, monkeypatch)
    set_ask(monkeypatch, home, ask)
    set_maintainer(home, maintainer)
    history = subjects(wiki)

    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"the filing must be accepted:\n{r.stdout}\n{r.stderr}"
    assert len(subjects(wiki)) == len(history) + 1, (
        f"an accepted operation records exactly one commit: {subjects(wiki)}"
    )
    return r, wiki


# The catalog's grammar as system/contracts/wiki-layout.md states it, read here
# independently of the implementation: an ordinary markdown link whose target is
# a wiki-relative `.md` path. An outbound URL in an annotation is not a catalog
# line, so it is not one here either.
CATALOG_LINK = re.compile(r"\]\(\s*([^()\s]+)\s*\)")


def catalog(wiki):
    """The page paths `index.md` links, in the order the file lists them."""
    text = (wiki / "index.md").read_text()
    return [
        target
        for target in CATALOG_LINK.findall(text)
        if "://" not in target and target.split("#", 1)[0].endswith(".md")
    ]


def index_lines(wiki):
    """`index.md` as lines — what a reconciliation that appends leaves alone, and
    a reconciliation that regenerates does not."""
    return (wiki / "index.md").read_text().splitlines()


def rejected(home, monkeypatch, maintainer, ask=ASK_VERIFIES):
    """File a second video with a maintainer that breaks one rule, and hold the
    run to the promise every rejection makes: exit 1, and a wiki byte-identical
    to the commit it started from, with no commit of its own. Returns the run so
    the caller can read the violation off stderr. Nothing is pending in the
    working tree here, so the pre-run commit is the tip of the history."""
    wiki = filed(home, monkeypatch)
    set_ask(monkeypatch, home, ask)
    set_maintainer(home, maintainer)
    before, history = snapshot(wiki), subjects(wiki)

    r = wiki_file(home, NEXT)
    assert r.returncode == 1, (
        f"the wiki must not be accepted:\n{r.stdout}\n{r.stderr}"
    )
    assert r.stderr.strip(), "a rejection that says nothing cannot be acted on"
    assert snapshot(wiki) == before, "a rejected operation leaves nothing behind"
    assert subjects(wiki) == history, "a rejected operation records no commit"
    return r


# --- sweeping a whole library (SPEC-wiki-003, SPEC-wiki-005) ------------------
#
# Both sweeps file every eligible video in one pass, in one pinned order, so the
# fixture library has to make that order observable and falsifiable: four videos
# whose chronology disagrees with their alphabet, two of them uploaded on the same
# day so the tiebreak is exercised, and none of them created on disk in the order
# the sweep must produce.

SWEEP = (
    # id, upload_date, title
    ("oldest00001", "2019-03-04", "The First Broadcast"),
    ("middle00002", "2021-07-09", "The Middle Years"),
    ("tie-alpha-1", "2023-05-05", "Same Day, First By Id"),
    ("tie-zebra-2", "2023-05-05", "Same Day, Second By Id"),
)

# upload_date ascending, ties broken by id — the order the wiki must accumulate in.
SWEEP_ORDER = [vid for vid, _, _ in SWEEP]

# neither that order nor its reverse: a sweep that files in creation or readdir
# order fails on this library rather than passing by luck.
CREATION_ORDER = ["tie-zebra-2", "middle00002", "tie-alpha-1", "oldest00001"]

SWEEP_METAS = {
    vid: {
        "id": vid,
        "title": title,
        "channel": "Sweep Channel",
        "upload_date": upload_date,
        "duration_s": 600,
        "url": f"https://www.youtube.com/watch?v={vid}",
    }
    for vid, upload_date, title in SWEEP
}


def unfiled_library(home, pages=None):
    """The library a sweep walks: four eligible videos, none of them filed.
    `pages` narrows which of them archive has rendered — a video with no page is
    a job that cannot be done yet, and the sweep's business is to notice rather
    than to fail."""
    if pages is None:
        pages = SWEEP_ORDER
    for vid in CREATION_ORDER:
        meta = SWEEP_METAS[vid]
        add_video(home, meta, [{"start": 0.0, "end": 4.0, "text": f"Fixture {vid}."}])
        if vid in pages:
            write_archive_page(home, meta, CH_SECTIONS)


# The honest maintainer, recording which video it was handed each time it ran.
# The record is the sweep's order, its skips and its stopping point all at once:
# a video the sweep passed over never appears in it.
RECORDS_EACH_ID = (
    SH
    + """
echo "$TAPEDECK_VIDEO_ID" >> "$TAPEDECK_HOME/maintainer-ids"
"""
    + FILES_THE_VIDEO
    + LOGS_IT
)


def maintainer_ids(home):
    """Every video the maintainer was invoked for, in the order it was invoked."""
    record = home / "maintainer-ids"
    return record.read_text().split() if record.is_file() else []


def links_to_nothing_for(video_id):
    """A maintainer that works honestly on every video except one, whose page it
    leaves pointing at a page that does not exist. The gate rejects that one
    filing; whether the rest of the sweep survives it is the question."""
    return RECORDS_EACH_ID + f"""
if [ "$TAPEDECK_VIDEO_ID" = "{video_id}" ]; then
  echo "Compare with [[nonexistent-page]]." >> "sources/$TAPEDECK_VIDEO_ID.md"
fi
"""


ENTRY_PARTS = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] (\S+) \| (.+)$", re.MULTILINE)


def log_entries(wiki):
    """The chronology as `(op, subject)` pairs, oldest first — what the wiki
    itself says happened, and in which order."""
    return ENTRY_PARTS.findall((wiki / "log.md").read_text())


def summary_line(r):
    """The sweep's closing one-liner. Which stream it lands on is the
    implementation's business; that one line accounts for every outcome at once
    is not — a sweep over a hundred videos whose result has to be reconstructed
    by reading a hundred lines has not reported anything."""
    lines = [
        line
        for line in (r.stdout + "\n" + r.stderr).splitlines()
        if all(word in line.lower() for word in ("filed", "skip", "fail"))
    ]
    assert len(lines) == 1, (
        f"expected exactly one line summarizing filed / already filed / skipped / "
        f"failed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    return lines[0]
