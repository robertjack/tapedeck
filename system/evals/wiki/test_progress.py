"""Durable evals: live progress from the maintainer run (SPEC-wiki-007).

Boundary: `python -m wiki file <id>` and `python -m wiki tend`; the maintainer
seam faked through config.toml, ask through $TAPEDECK_ASK_CMD
(system/evals/wiki/wikilib.py).

A maintainer run is minutes long and used to be silent from start to exit. This
suite pins the three promises that replace the silence: every run announces
itself on stderr before the agent speaks; a maintainer that emits Claude Code
stream events gets each one rendered as a progress line *as it arrives*, not
after exit; and the run's product is untouched by any of it — a streaming tend
still hands the user prose, a plain maintainer still hands over its stdout byte
for byte, and no raw event JSON ever lands on stdout.

The liveness eval is the load-bearing one. An implementation that collects the
whole stream and prints "progress" afterwards would pass every content
assertion here and still look frozen for the length of the run — so the fake
emits its first event, then sleeps longer than the deadline the eval holds it
to. Only a run that relays events while the agent is still working can meet it.
"""

import os
import shlex
import subprocess
import sys
import threading
import time

from conftest import REPO, run_component, set_maintainer
from wikilib import (
    FILED,
    FILES_THE_VIDEO,
    GOOD,
    LOGS_IT,
    SH,
    filed,
    set_ask,
    stocked,
    wiki_file,
)

MODEL_LINE = '{"type":"system","subtype":"init","model":"fixture-model-9"}'
READS_A_PROBE = (
    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
    '"name":"Read","input":{"file_path":"sources/probe.md"}}]}}'
)
EDITS_A_NOTE = (
    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
    '"name":"Edit","input":{"file_path":"notes/regeneration.md"}}]}}'
)
RESULT = '{"type":"result","subtype":"success","result":"filed the fixture video"}'

FINDINGS = "regeneration is asserted on two pages and argued on neither"
REPORT_RESULT = (
    '{"type":"result","subtype":"success","result":"' + FINDINGS + '"}'
)


def emit(line):
    return f"echo '{line}'\n"


# A streaming maintainer that does the same honest work as GOOD, narrating it
# in the JSONL a headless `claude -p --output-format stream-json` produces.
STREAMS = (
    SH
    + emit(MODEL_LINE)
    + emit(READS_A_PROBE)
    + FILES_THE_VIDEO
    + emit(EDITS_A_NOTE)
    + LOGS_IT
    + emit(RESULT)
)

# Emits one event, then sleeps past the liveness deadline before finishing the
# work: the probe line can only arrive on time if events are relayed live.
STREAMS_THEN_STALLS = (
    SH
    + emit(READS_A_PROBE)
    + "sleep 6\n"
    + FILES_THE_VIDEO
    + LOGS_IT
    + emit(RESULT)
)

# A streaming tend in report mode: reads, finds one thing, writes nothing.
STREAMS_A_REPORT = SH + emit(MODEL_LINE) + emit(REPORT_RESULT)

# The maintainer a user configured before streaming existed: prose on stdout.
SPEAKS_PLAINLY = SH + f"echo '{FINDINGS}'\n"

DEADLINE = 4.0  # seconds; the stalling fake sleeps 6, so late means buffered


# --- the run is visible -----------------------------------------------------


def test_a_run_announces_itself_before_the_agent_speaks(home, monkeypatch):
    """GOOD emits nothing at all, so whatever names the run on stderr came from
    tapedeck: even a silent maintainer no longer looks like a hang."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, GOOD)
    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert FILED in r.stderr, (
        f"nothing on stderr names the run that just spent an agent invocation "
        f"on {FILED}:\n{r.stderr!r}"
    )


def test_stream_events_become_progress_lines(home, monkeypatch):
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, STREAMS)
    r = wiki_file(home, FILED)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    assert "fixture-model-9" in r.stderr, (
        f"initialization should name the model that answered:\n{r.stderr!r}"
    )
    for tool, touched in (("Read", "sources/probe.md"), ("Edit", "notes/regeneration.md")):
        assert tool in r.stderr and touched in r.stderr, (
            f"a {tool} of {touched} happened and the feed never said so:\n{r.stderr!r}"
        )
    assert '"type"' not in r.stdout, (
        f"raw stream events belong to the feed, never to stdout:\n{r.stdout!r}"
    )


def test_progress_arrives_while_the_maintainer_still_runs(home, monkeypatch):
    """The difference between progress and a post-mortem, held to a clock: the
    fake emits its Read event and then sleeps for 6 seconds, so the probe line
    reaching stderr inside 4 proves events are relayed as they arrive."""
    stocked(home)
    set_ask(monkeypatch, home)
    set_maintainer(home, STREAMS_THEN_STALLS)

    cmd = os.environ.get("TAPEDECK_WIKI_CMD", f"{sys.executable} -m wiki")
    process = subprocess.Popen(
        [*shlex.split(cmd), "file", FILED],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "TAPEDECK_HOME": str(home),
            "PYTHONPATH": os.pathsep.join(
                [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        },
    )
    started = time.monotonic()
    arrivals = []

    def watch():
        for line in process.stderr:
            arrivals.append((time.monotonic() - started, line))

    reader = threading.Thread(target=watch)
    reader.start()
    try:
        process.wait(timeout=60)
    finally:
        process.kill()
        reader.join(timeout=10)

    probes = [t for t, line in arrivals if "probe" in line]
    assert probes, (
        f"the Read event never became a progress line at all:\n"
        f"{[line for _, line in arrivals]!r}"
    )
    assert min(probes) < DEADLINE, (
        f"the probe line arrived {min(probes):.1f}s in — after the maintainer's "
        f"sleep, which means the stream was collected instead of relayed"
    )


# --- the product is untouched -------------------------------------------------


def test_the_raw_stream_never_reaches_the_product(home, monkeypatch):
    """tend's report reaches the user as prose in the maintainer's voice
    (SPEC-wiki-006) whichever kind of maintainer produced it: a streaming run's
    product is its result event's text, nothing more."""
    filed(home, monkeypatch)
    set_maintainer(home, STREAMS_A_REPORT)
    r = run_component("wiki", ["tend"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert FINDINGS in r.stdout, (
        f"the finding never reached the user:\n{r.stdout!r}"
    )
    assert '{"type"' not in r.stdout, (
        f"the report is the result's text, not the stream that carried it:\n{r.stdout!r}"
    )


def test_a_plain_maintainer_keeps_its_stdout(home, monkeypatch):
    """The seam holds any command (SPEC-core-004): an agent that narrates
    nothing and prints prose is not degraded by the streaming path existing."""
    filed(home, monkeypatch)
    set_maintainer(home, SPEAKS_PLAINLY)
    r = run_component("wiki", ["tend"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert FINDINGS in r.stdout, (
        f"a plain maintainer's stdout is the product, byte for byte:\n{r.stdout!r}"
    )


# --- the default watches ------------------------------------------------------


def test_an_unconfigured_seam_suggests_a_streaming_agent(home):
    """The message that teaches the seam suggests the shipped default, and the
    shipped default is one whose runs can be watched."""
    stocked(home)
    r = wiki_file(home, FILED)
    assert r.returncode == 2, f"{r.stdout}\n{r.stderr}"
    assert "stream-json" in r.stderr, (
        f"the suggested maintainer_command should stream:\n{r.stderr!r}"
    )
