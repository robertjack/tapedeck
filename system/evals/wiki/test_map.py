"""Durable evals: the maintainer is shown the wiki instead of made to find it
(SPEC-wiki-009).

Boundary: `python -m wiki file <id>` and `python -m wiki tend`; the maintainer
seam faked through config.toml, ask through $TAPEDECK_ASK_CMD
(system/evals/wiki/wikilib.py).

The filing task asks the maintainer to connect a video to what the wiki already
holds, and hands it Read, Grep and Glob to find out what that is. So it reads
broadly and guesses: across the user's ten filings the number of *existing* notes
each run rewrote went 0, 0, 3, 2, 9, 12, 12, 13, 20, 15, against notes averaging
20KB. Linear in the size of the wiki, and about 75,000 input tokens a filing.

A line per page costs about 100 bytes. These evals hold the map to being complete
(every page, so nothing is invisible), bounded (a line, never a body), ranked
where ranking is possible, and absent from the wiki itself — it travels in the
task and is a file nowhere, because a file would be a page and a page is judged.

The shortlist is identified without pinning a single word of the task's wording:
it is a separate list naming a few of the map's pages *again*, so a page on it
appears twice in the task and a page merely in the map appears once. That is the
whole of what "shortlist" has to mean for it to be worth anything.
"""

from conftest import run_component
from wikilib import (
    FILED,
    NEXT,
    RECORDS_THE_TASK,
    filed,
    set_ask,
    set_maintainer,
    snapshot,
    stocked,
    task_given,
    wiki_file,
)

# The archive page NEXT is filed from is about sourdough: starters, proofing,
# scoring loaves (wikilib.BREAD_SECTIONS). One of these notes shares that
# vocabulary and the rest deliberately do not, so a ranking that works and a
# ranking that returns the first few pages alphabetically are distinguishable.
KIN = "notes/proofing-and-starters.md"
KIN_HEADING = "Proofing and starters"
KIN_BODY = (
    "Sourdough starters are the whole game. Proofing times decide the crumb, and "
    "scoring loaves decides the ear. Block one and block two of any bread course "
    "are really one lesson about proofing."
)

STRANGERS = {
    "notes/orbital-mechanics.md": (
        "Orbital mechanics",
        "Hohmann transfers, inclination changes, delta-v budgets and the rocket "
        "equation. Nothing here concerns baking.",
    ),
    "notes/medieval-taxation.md": (
        "Medieval taxation",
        "Tithes, scutage and the exchequer. Assessment rolls and the sheriff's "
        "farm. Nothing here concerns baking.",
    ),
    "notes/typeface-history.md": (
        "Typeface history",
        "Garamond, Baskerville, the transitional serif and the arrival of the "
        "grotesque. Nothing here concerns baking.",
    ),
    "notes/harbour-dredging.md": (
        "Harbour dredging",
        "Silt, spoil grounds, cutter suction and the maintenance interval of a "
        "navigable channel. Nothing here concerns baking.",
    ),
}

# A page whose body dwarfs its heading — what the map must not inline.
BLOATED = "notes/the-long-one.md"
BLOATED_HEADING = "The long one"
BLOATED_TELL = "distinctive-sentence-that-must-not-reach-the-task"
BLOATED_BODY = (BLOATED_TELL + " padding padding padding.\n") * 200

# No line describing a page is a paragraph. Generous — the point is that it is
# bounded at all, not where exactly the bound sits.
LINE_BUDGET = 300


def stock_the_wiki(home, monkeypatch):
    """A filed wiki with pages worth telling the maintainer about. They are
    written by hand, which is how a co-authored wiki actually grows
    (system/contracts/wiki-layout.md) and which keeps this fixture independent of
    what any maintainer fake chooses to write."""
    wiki = filed(home, monkeypatch)
    pages = {KIN: (KIN_HEADING, KIN_BODY), BLOATED: (BLOATED_HEADING, BLOATED_BODY)}
    pages.update(STRANGERS)
    for where, (heading, body) in pages.items():
        (wiki / where).write_text(f"# {heading}\n\n{body}\n", encoding="utf-8")
    return wiki


def every_page(wiki):
    """Every page the map owes the maintainer a line for: everything but the
    three pinned files."""
    return sorted(
        str(page.relative_to(wiki))
        for page in wiki.rglob("*.md")
        if ".git" not in page.relative_to(wiki).parts
        and str(page.relative_to(wiki)) not in ("CLAUDE.md", "index.md", "log.md")
    )


def file_next_recording_the_task(home, monkeypatch):
    """File NEXT into the stocked wiki with a maintainer that keeps its task.

    Returns the task, the wiki, and **the pages that existed when the map was
    built** — which is not the same as the pages that exist afterwards. The map is
    assembled before the agent runs, so the pages this very run creates cannot be
    in it, and an eval that compared the task against the post-run directory would
    be asking the map to have described the future.
    """
    wiki = stock_the_wiki(home, monkeypatch)
    before = every_page(wiki)
    set_maintainer(home, RECORDS_THE_TASK)
    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    return task_given(home), wiki, before


# --- the map is complete ------------------------------------------------------


def test_the_task_carries_a_line_for_every_page(home, monkeypatch):
    """A page the map omits is a page the maintainer cannot know exists, which is
    the state this clause is replacing. Completeness is also what stops the
    shortlist from quietly becoming the whole of what the agent can see."""
    task, _, before = file_next_recording_the_task(home, monkeypatch)
    for page in before:
        assert page in task, (
            f"{page} was in the wiki when the map was built and is absent from the "
            f"task, so the maintainer can only find it by reading the directory:\n{task}"
        )


def test_a_map_line_carries_the_pages_own_heading(home, monkeypatch):
    """A path alone makes the reader open every page to learn which one it
    wanted, which is the cost being removed."""
    task, _, _ = file_next_recording_the_task(home, monkeypatch)
    for heading in (KIN_HEADING, *(h for h, _ in STRANGERS.values())):
        assert heading in task, (
            f"no line in the task names the page titled {heading!r}:\n{task}"
        )


def test_a_page_contributes_a_line_and_never_its_body(home, monkeypatch):
    """The bound is the entire point. A map that inlines page bodies is the 557KB
    of prose it was built to avoid, delivered by a different route."""
    task, _, _ = file_next_recording_the_task(home, monkeypatch)
    assert BLOATED_TELL not in task, (
        f"the map carried a page's body into the task, not a line about it:\n{task}"
    )
    described = [line for line in task.splitlines() if BLOATED in line]
    assert described, f"the long page got no line at all:\n{task}"
    assert len(described[0]) <= LINE_BUDGET, (
        f"the line describing {BLOATED} is {len(described[0])} characters; a map "
        f"whose lines are unbounded grows like the thing it replaces: {described[0]!r}"
    )


# --- the shortlist ------------------------------------------------------------


def mentions(task, page):
    return task.count(page)


def test_the_shortlist_names_the_pages_that_share_the_videos_vocabulary(home, monkeypatch):
    """The sourdough note and four pages about dredging, taxation, typefaces and
    orbits. A ranking that means anything puts the first ahead of the rest.

    What this does *not* demand is a shortlist of only relevant pages. The
    shortlist is the top of a ranking, and a ranking of five pages with one good
    match will fill its remaining slots with bad ones however well it works — a
    top-3 here cannot avoid naming two strangers. Failing that would be failing
    the implementation for the fixture's shape. The honest bar is that the kin is
    on the list and the list discriminates: at least one stranger left off.
    """
    task, _, _ = file_next_recording_the_task(home, monkeypatch)
    assert mentions(task, KIN) > 1, (
        f"{KIN} shares this video's whole vocabulary and was not shortlisted — it "
        f"appears {mentions(task, KIN)} time(s) in the task:\n{task}"
    )
    passed_over = [page for page in STRANGERS if mentions(task, page) <= 1]
    assert passed_over, (
        f"every page in the wiki was shortlisted, including four with nothing in "
        f"common with this video — the ranking is not ranking:\n{task}"
    )


def test_the_shortlist_does_not_replace_the_map(home, monkeypatch):
    """A shortlist that stands in for the map hides exactly the pages a
    maintainer would otherwise have discovered for itself."""
    task, wiki, _ = file_next_recording_the_task(home, monkeypatch)
    listed_once = [page for page in STRANGERS if mentions(task, page) >= 1]
    assert len(listed_once) == len(STRANGERS), (
        f"only {len(listed_once)} of {len(STRANGERS)} unrelated pages reached the "
        f"task at all; the shortlist has replaced the map:\n{task}"
    )


def test_a_shortlist_as_long_as_the_map_is_not_a_shortlist(home, monkeypatch):
    """Six pages here, and a shortlist naming all of them has ranked nothing."""
    task, wiki, _ = file_next_recording_the_task(home, monkeypatch)
    pages = every_page(wiki)
    twice = [page for page in pages if mentions(task, page) > 1]
    assert len(twice) < len(pages), (
        f"every page in the wiki is on the shortlist, so it is the map again: {twice}"
    )


# --- the empty wiki -----------------------------------------------------------


def test_a_wiki_with_nothing_in_it_gets_no_map(home, monkeypatch):
    """The first filing of all. An empty map section reads to an agent as a wiki
    whose contents were withheld, which is worse than not raising the subject."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_THE_TASK)
    assert wiki_file(home, FILED).returncode == 0

    task = task_given(home)
    strays = [
        line
        for line in task.splitlines()
        if (".md" in line and ("notes/" in line or "sources/" in line))
        and f"sources/{FILED}.md" not in line
    ]
    assert not strays, (
        f"the task describes pages in a wiki that has none:\n" + "\n".join(strays)
    )


# --- tend ---------------------------------------------------------------------


def test_tend_is_shown_the_wiki_too(home, monkeypatch):
    """A tend is about the wiki entire, and the argument for telling it what is
    there is the filing's argument with more pages in it."""
    wiki = stock_the_wiki(home, monkeypatch)
    set_maintainer(home, RECORDS_THE_TASK)
    r = run_component("wiki", ["tend"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    task = task_given(home)
    for page in every_page(wiki):
        assert page in task, f"{page} was withheld from the tend's task:\n{task}"


# --- the map is not a file ----------------------------------------------------


def test_the_map_is_never_written_into_the_wiki(home, monkeypatch):
    """A file under wiki/ is a page: the gate would judge it, the catalog would
    have to list it, its links would have to resolve, and Obsidian would show it.
    The contract pins five entries as the whole tree."""
    wiki = stock_the_wiki(home, monkeypatch)
    before = set(snapshot(wiki))
    set_maintainer(home, RECORDS_THE_TASK)
    assert wiki_file(home, NEXT).returncode == 0

    appeared = set(snapshot(wiki)) - before
    assert appeared == {f"sources/{NEXT}.md", "notes/proofing.md"}, (
        f"the run left behind something other than the pages it wrote: {appeared}"
    )
