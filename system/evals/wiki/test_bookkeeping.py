"""Durable evals: tapedeck keeps the catalog and the chronology (SPEC-wiki-008).

Boundary: `python -m wiki file <id>`; the maintainer seam faked through
config.toml, ask through $TAPEDECK_ASK_CMD (system/evals/wiki/wikilib.py).

`index.md` and `log.md` used to be the maintainer's obligation, and the gate used
to reject a run that neglected either. Measured on a real ten-video wiki, that
obligation cost roughly 28,000 input tokens per filing — a 97KB chronology re-read
in full to append one line to it, a catalog re-read to append another — and both
grow with every operation until a filing no longer fits beside a transcript.
Neither is a judgment call, so neither is worth an agent's attention.

So the maintainer writes pages and stops, and tapedeck reconciles both files after
the agent exits and before the gate judges the result. These evals hold that to
three promises: the neglect is *accepted* rather than rejected; what tapedeck
appends is correct and complete; and it is genuinely appended — a catalog the
implementation regenerates would satisfy every completeness check here while
quietly overruling the brief's grouping on every run.

Two of these are cases test_gate.py used to own, inverted. That inversion is the
whole clause: what used to be a rejection, paid for with a maintainer run, is now
nothing at all.
"""

import re

from wikilib import (
    FILED,
    FILES_ONLY_THE_PAGES,
    GOOD,
    LINKS_TO_NOTHING,
    NEW_NOTE,
    NEW_NOTE_HEADING,
    NEXT,
    SH,
    WRITES_THE_PAGES,
    accepted,
    catalog,
    index_lines,
    log_entries,
    rejected,
    set_ask,
    set_maintainer,
    stocked,
    wiki_file,
)

SOURCE_PAGE = f"sources/{NEXT}.md"

# What a streaming maintainer reports about its own run. The product is the prose
# tapedeck has to carry into the entry; the figures beside it are what let the
# chronology answer "is this getting more expensive" without archaeology.
PRODUCT = "filed the sourdough video and opened a note on proofing"
RESULT_WITH_COST = (
    '{"type":"result","subtype":"success","result":"' + PRODUCT + '",'
    '"duration_ms":90000,"total_cost_usd":0.42,'
    '"usage":{"input_tokens":31000,"output_tokens":4200}}'
)
DURATION_S, COST, INPUT_TOKENS, OUTPUT_TOKENS = "90", "0.42", "31000", "4200"

STREAMS_ITS_COST = SH + WRITES_THE_PAGES + f"echo '{RESULT_WITH_COST}'\n"

# The maintainer a user configured before any of this: prose on stdout, no stream,
# no figures to record.
SPEAKS_PLAINLY = SH + WRITES_THE_PAGES + f"echo '{PRODUCT}'\n"

RECORDS_THE_TASK = '#!/bin/sh\ncat > "$TAPEDECK_HOME/task"\n' + WRITES_THE_PAGES

# A heading that opens like a chronology entry and is not one — what the log must
# never gain, whatever the maintainer did or did not report.
MALFORMED = re.compile(r"^## \[(?!\d{4}-\d{2}-\d{2}\] \S+ \| .)", re.MULTILINE)


def last_entry(wiki):
    """The entry this operation left, as text — everything from its heading on."""
    return "## [" + (wiki / "log.md").read_text().split("## [")[-1]


# --- the neglect is accepted --------------------------------------------------


def test_a_maintainer_that_writes_no_bookkeeping_is_accepted(home, monkeypatch):
    """The inversion, stated once. This maintainer writes its source page and a
    note and touches neither index.md nor log.md — two rejections under the gate
    as it stood, and a complete filing now."""
    r, _ = accepted(home, monkeypatch, FILES_ONLY_THE_PAGES)
    assert "error" not in r.stderr.lower(), (
        f"nothing about this filing is an error:\n{r.stderr!r}"
    )


# --- the catalog --------------------------------------------------------------


def test_a_new_page_reaches_the_catalog_without_the_maintainer(home, monkeypatch):
    """Both pages the run created are findable by someone who opens index.md,
    and the agent catalogued neither."""
    _, wiki = accepted(home, monkeypatch, FILES_ONLY_THE_PAGES)
    listed = catalog(wiki)
    for page in (SOURCE_PAGE, NEW_NOTE):
        assert page in listed, (
            f"{page} was written and never catalogued — the catalog is how a page "
            f"is found at all: {listed}"
        )


def test_the_catalog_line_carries_the_pages_own_heading(home, monkeypatch):
    """A line that is only a path makes the reader open every page to find one.
    The page's opening heading is the one annotation tapedeck can know."""
    _, wiki = accepted(home, monkeypatch, FILES_ONLY_THE_PAGES)
    lines = [line for line in index_lines(wiki) if NEW_NOTE in line]
    assert lines, f"no catalog line mentions {NEW_NOTE}: {index_lines(wiki)}"
    assert NEW_NOTE_HEADING in lines[0], (
        f"the catalog line should name the page, not just its path: {lines[0]!r}"
    )


def test_the_catalog_is_appended_to_never_regenerated(home, monkeypatch):
    """Grouping, ordering and annotation belong to the brief
    (system/contracts/wiki-layout.md). A reconciliation that rewrites the file
    passes every completeness check above while overruling the user on every run,
    so what was already there has to survive, in order, byte for byte."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, GOOD)
    assert wiki_file(home, NEXT).returncode == 0
    wiki = home / "wiki"

    # The user's own arrangement, made before the next filing touches anything.
    arranged = ["# Catalog", "", "## The ones that matter", *index_lines(wiki), ""]
    (wiki / "index.md").write_text("\n".join(arranged) + "\n")

    set_maintainer(home, FILES_ONLY_THE_PAGES)
    assert wiki_file(home, FILED).returncode == 0
    after = index_lines(wiki)
    assert after[: len(arranged)] == arranged, (
        f"the catalog was regenerated rather than appended to; the user's headings "
        f"and order did not survive:\n{after}"
    )


# --- the chronology -----------------------------------------------------------


def test_the_operation_reaches_the_chronology_without_the_maintainer(home, monkeypatch):
    """An accepted operation owes the history a line, and owing it to the agent is
    what made every filing read a 97KB file first."""
    _, wiki = accepted(home, monkeypatch, FILES_ONLY_THE_PAGES)
    assert [op for op, _ in log_entries(wiki)] == ["file", "file"], (
        f"the fixture filing and this one, one entry each: {log_entries(wiki)}"
    )


def test_a_silent_maintainer_still_gets_a_well_formed_entry(home, monkeypatch):
    """FILES_ONLY_THE_PAGES prints nothing at all. The operation still happened,
    so the chronology still records it — with a subject, not an empty one."""
    _, wiki = accepted(home, monkeypatch, FILES_ONLY_THE_PAGES)
    op, subject = log_entries(wiki)[-1]
    assert op == "file", f"the operation names itself: {log_entries(wiki)}"
    assert subject.strip(), "an entry whose subject is blank records nothing"
    assert not MALFORMED.search((wiki / "log.md").read_text()), (
        "the log gained a heading that opens like an entry and is not one"
    )


def test_the_entry_carries_what_the_maintainer_reported(home, monkeypatch):
    """The agent's own account of the run is the only prose anyone can write about
    it, and SPEC-wiki-007 already extracts it from the stream."""
    _, wiki = accepted(home, monkeypatch, STREAMS_ITS_COST)
    log = (wiki / "log.md").read_text()
    assert PRODUCT in log, (
        f"the maintainer said what it did and the chronology did not keep it:\n{log}"
    )
    assert '"type"' not in log, f"the entry is the product, not the stream:\n{log}"


def test_an_entry_the_maintainer_wrote_is_left_alone(home, monkeypatch):
    """A maintainer configured to write its own chronology is not doing anything
    wrong, and two entries for one operation is a worse record than none. GOOD
    still writes its own, so tapedeck must add nothing beside it."""
    _, wiki = accepted(home, monkeypatch, GOOD)
    entries = log_entries(wiki)
    assert len(entries) == 2, (
        f"exactly one entry per operation, whoever wrote it: {entries}"
    )
    assert entries[-1] == ("file", NEXT), (
        f"the agent's own entry stands as it wrote it: {entries}"
    )


# --- what the run cost --------------------------------------------------------


def test_a_streaming_run_records_what_it_cost(home, monkeypatch):
    """The measurement this clause exists to make possible: the next person asking
    whether the wiki is getting more expensive reads the log, instead of
    reconstructing it from commit timestamps."""
    _, wiki = accepted(home, monkeypatch, STREAMS_ITS_COST)
    entry = last_entry(wiki)
    for figure, what in (
        (DURATION_S, "how long the run took, in whole seconds"),
        (COST, "what it cost"),
        (INPUT_TOKENS, "how many tokens went in"),
        (OUTPUT_TOKENS, "how many came out"),
    ):
        assert figure in entry, f"the entry does not record {what} ({figure}):\n{entry}"


def test_a_maintainer_that_does_not_stream_still_logs_cleanly(home, monkeypatch):
    """Any command is a legal maintainer (SPEC-core-004). One that reports no
    figures contributes none — not a malformed entry, and not a row of zeroes that
    would read as a free run forever after."""
    _, wiki = accepted(home, monkeypatch, SPEAKS_PLAINLY)
    entry = last_entry(wiki)
    assert PRODUCT in entry, f"the plain maintainer's product is still its entry:\n{entry}"
    assert not MALFORMED.search((wiki / "log.md").read_text()), (
        "an unmeasured run must not malform the log"
    )
    assert "0.0" not in entry and "$0" not in entry, (
        f"a run whose price is unknown has no price line, not a zero:\n{entry}"
    )


# --- the task stops asking ----------------------------------------------------


def test_the_task_no_longer_asks_the_maintainer_for_bookkeeping(home, monkeypatch):
    """The saving is in the task, not the gate. As long as the instructions name
    these files a competent agent will open them, and opening log.md is the 24,000
    tokens this clause is about."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, RECORDS_THE_TASK)
    r = wiki_file(home, NEXT)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    task = (home / "task").read_text()
    for name in ("log.md", "index.md"):
        assert name not in task, f"the task still sends the maintainer to {name}:\n{task}"


def test_the_scaffolded_brief_does_not_hand_them_back(home, monkeypatch):
    """The brief is read on every run of every fresh install, and the default
    tapedeck ships lists the catalog and the chronology among the things an
    operation is judged on — which is an instruction to go and maintain them.
    Wherever it still names either file it has to say whose they are. The user's
    own brief is untouched by this: it is theirs from the scaffold onwards."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, FILES_ONLY_THE_PAGES)
    assert wiki_file(home, NEXT).returncode == 0

    brief = (home / "wiki" / "CLAUDE.md").read_text()
    for line in brief.splitlines():
        for name in ("index.md", "log.md"):
            if name in line:
                assert "tapedeck" in line.lower(), (
                    f"the brief names {name} without saying tapedeck keeps it, so a "
                    f"maintainer reading it will go and maintain it: {line!r}"
                )


# --- a refusal takes the bookkeeping with it ----------------------------------


def test_a_rejected_operation_appends_no_bookkeeping(home, monkeypatch):
    """Reconciliation happens before the gate so the gate judges what is actually
    committed — which means a refusal has to roll it back too. A wiki that keeps
    the catalog line for a page the rejection deleted has a catalog pointing at
    nothing. `rejected` already asserts the whole tree is byte-identical to the
    pre-run commit; naming the two files is what makes the failure legible."""
    rejected(home, monkeypatch, LINKS_TO_NOTHING)
    wiki = home / "wiki"
    assert len(log_entries(wiki)) == 1, (
        f"the refused operation wrote itself into the history anyway: "
        f"{log_entries(wiki)}"
    )
    assert NEXT not in (wiki / "index.md").read_text(), (
        "the refused operation's page is still catalogued"
    )
