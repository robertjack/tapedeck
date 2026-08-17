"""Durable evals: `tapedeck doctor` (SPEC-cli-007).

Boundary: the `tapedeck` executable, library via $TAPEDECK_HOME.

Everything doctor says about the seams is driven from a fixture `config.toml`,
so these tests pin the derivation — seam -> head executable -> PATH — and never
the particular tools this machine happens to own. `sh` stands in for "a command
that resolves" (conftest already shells out to it everywhere); MISSING stands in
for one that cannot. The two checks that genuinely read the machine, `fts5` and
`platform`, are asserted against what this eval process can see for itself,
never against a hardcoded expectation about the host.
"""

import json
import platform
import re
import shutil
import sys

import pytest

from conftest import run_cli

MISSING = "tapedeck-no-such-tool-2f9c1a"

# SPEC-cli-007 pins the checks and their order: the seams by dotted config key,
# then what the derivation chain needs whatever tools fill it.
CHECKS = (
    "ingest.fetcher_command",
    "ingest.lister_command",
    "transcribe.transcriber_command",
    "ask.librarian_command",
    "ask.answerer_command",
    "wiki.maintainer_command",
    "ffmpeg",
    "home",
    "fts5",
    "platform",
)
SEAMS = CHECKS[:6]
STATUSES = {"pass", "fail", "optional"}

APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"


def write_config(
    home,
    *,
    fetcher="sh -c :",
    lister="sh -c :",
    transcriber="sh -c :",
    model="fixture/whisper-0",
    librarian="sh -c :",
    answerer="sh -c :",
):
    """A config.toml with each seam pointed wherever this test needs it.
    `None` leaves the key out of the file entirely."""
    lines = ["[ingest]"]
    if fetcher is not None:
        lines.append(f'fetcher_command = "{fetcher}"')
    if lister is not None:
        lines.append(f'lister_command = "{lister}"')
    lines += ["", "[transcribe]"]
    if transcriber is not None:
        lines.append(f'transcriber_command = "{transcriber}"')
    lines.append(f'model = "{model}"')
    if librarian is not None or answerer is not None:
        lines += ["", "[ask]"]
        if librarian is not None:
            lines.append(f'librarian_command = "{librarian}"')
        if answerer is not None:
            lines.append(f'answerer_command = "{answerer}"')
    (home / "config.toml").write_text("\n".join(lines) + "\n")


def doctor(home, *args):
    """Run `tapedeck doctor --json` and return (result, {check: row})."""
    r = run_cli(["doctor", "--json", *args], home)
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        raise AssertionError(
            f"`doctor --json` did not emit JSON (exit {r.returncode}):\n"
            f"stdout={r.stdout!r}\nstderr={r.stderr!r}"
        ) from exc
    return r, {row["check"]: row for row in rows}


def failures(rows):
    return sorted(name for name, row in rows.items() if row["status"] == "fail")


def test_a_seam_command_is_checked_by_resolving_its_head_executable(home):
    """(i) an existing executable passes, (ii) a nonexistent one fails — and the
    failure is what decides the exit code."""
    write_config(home, fetcher="sh /nowhere/fetch.sh", transcriber=f"{MISSING} --model large")
    r, rows = doctor(home)

    assert rows["ingest.fetcher_command"]["status"] == "pass", (
        "the fetcher's head executable is `sh`, which resolves — doctor checks the head "
        "on PATH, not whether the script file behind it exists"
    )
    bad = rows["transcribe.transcriber_command"]
    assert bad["status"] == "fail"
    assert MISSING in bad["detail"], (
        f"the reason must name the executable that could not be found: {bad['detail']!r}"
    )
    assert r.returncode == 1, "a required seam that cannot resolve is exit 1"


def test_a_seam_that_begins_with_environment_assignments_resolves_its_real_program(home):
    """SPEC-cli-010. `VAR=value cmd args` is how a shell sets one variable for one
    command, and it is how the user's own transcriber is configured:

        HF_HUB_OFFLINE=1 parakeet-mlx --output-format json ...

    Taking the first shell word made doctor report `HF_HUB_OFFLINE=1: not on PATH`,
    so a working installation showed one failed check from the day that line was
    written. A health check that cries wolf teaches the user to skim past the row
    that will one day matter.
    """
    write_config(home, transcriber="FOO=1 BAR=2 sh /nowhere/whisper.sh --model large")
    r, rows = doctor(home)
    seam = rows["transcribe.transcriber_command"]
    assert seam["status"] == "pass", (
        f"the program here is `sh`, which resolves; the leading assignments are the "
        f"shell's business, not a missing executable: {seam['detail']!r}"
    )
    assert "sh" in seam["detail"] and "FOO=1" not in seam["detail"], (
        f"the row must name the program that resolved, never the assignment: "
        f"{seam['detail']!r}"
    )
    assert r.returncode == 0, (
        f"one healthy seam misread as broken must not fail the whole diagnosis:\n{r.stdout}"
    )


def test_an_assignment_prefixed_seam_whose_program_is_missing_still_fails(home):
    """The fix reads past assignments; it does not stop checking. A command whose
    real program is absent is still a failure, and the reason still names it."""
    write_config(home, transcriber=f"FOO=1 {MISSING} --model large")
    _, rows = doctor(home)
    seam = rows["transcribe.transcriber_command"]
    assert seam["status"] == "fail", f"the program is absent: {seam['detail']!r}"
    assert MISSING in seam["detail"], (
        f"the reason must name the executable that could not be found, not the "
        f"assignment in front of it: {seam['detail']!r}"
    )


def test_the_checks_are_derived_from_the_seams_not_from_a_tool_list(home):
    """Swap a seam to a different tool and doctor looks for the different tool.
    Nothing here knows the word yt-dlp."""
    write_config(home, fetcher=f"{MISSING}-downloader --best")
    _, rows = doctor(home)
    assert rows["ingest.fetcher_command"]["status"] == "fail"
    assert f"{MISSING}-downloader" in rows["ingest.fetcher_command"]["detail"]

    write_config(home, fetcher="sh -c 'echo mine'")
    _, rows2 = doctor(home)
    assert rows2["ingest.fetcher_command"]["status"] == "pass", (
        "a seam pointed at any resolvable command passes; doctor has no opinion "
        "about which downloader a user runs (SPEC-core-004)"
    )


def test_a_required_seam_missing_from_config_is_a_failure(home):
    write_config(home, lister=None)
    r, rows = doctor(home)
    assert rows["ingest.lister_command"]["status"] == "fail", (
        "an [ingest] seam absent from config.toml leaves nothing for `add` to run"
    )
    assert r.returncode == 1


def test_an_absent_ask_seam_is_optional_and_never_fails_the_run(home):
    write_config(home, librarian=None, answerer=None)
    r, rows = doctor(home)

    for key in ("ask.librarian_command", "ask.answerer_command"):
        assert rows[key]["status"] == "optional", (
            f"{key} is not required: ask needs it, search does not (SPEC-cli-007)"
        )
        detail = rows[key]["detail"].lower()
        assert "ask" in detail and "search" in detail, (
            f"the optional reason must say which half of the tool it costs: {detail!r}"
        )

    if shutil.which("ffmpeg") is None:  # a real, required gap on this host, not doctor's fault
        pytest.skip("ffmpeg is genuinely absent here, so exit 1 would be the right answer")
    assert r.returncode == 0, (
        "an unconfigured [ask] seam must not decide the exit code; doctor failed on: "
        f"{failures(rows)}"
    )


def test_an_unresolvable_ask_seam_is_optional_too(home):
    write_config(home, librarian=f"{MISSING}-agent -p", answerer=None)
    r, rows = doctor(home)
    assert rows["ask.librarian_command"]["status"] == "optional"
    assert "ask.librarian_command" not in failures(rows)
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is genuinely absent here, so exit 1 would be the right answer")
    assert r.returncode == 0, f"optional results never make it 1; failures: {failures(rows)}"


def test_json_is_every_check_in_the_pinned_order(home):
    write_config(home)
    r = run_cli(["doctor", "--json"], home)
    rows = json.loads(r.stdout)

    assert isinstance(rows, list) and rows, "--json emits a list of checks"
    assert [row["check"] for row in rows] == list(CHECKS), (
        "every check is reported in the fixed order, passes included — a diagnosis that "
        "prints only complaints cannot tell 'checked and fine' from 'never looked'"
    )
    for row in rows:
        assert set(row) == {"check", "status", "detail"}, f"unexpected keys in {row!r}"
        assert row["status"] in STATUSES, f"{row['check']}: bad status {row['status']!r}"
        assert isinstance(row["detail"], str) and row["detail"].strip(), (
            f"{row['check']} carries no reason"
        )
    assert "\x1b" not in r.stdout


def test_exit_code_follows_the_failures_and_nothing_else(home):
    write_config(home)
    r, rows = doctor(home)
    assert (r.returncode == 0) == (failures(rows) == []), (
        f"exit {r.returncode} disagrees with the report; failures: {failures(rows)}"
    )
    assert r.returncode in (0, 1)


def test_fts5_is_checked_and_available_here(home):
    write_config(home)
    _, rows = doctor(home)
    assert rows["fts5"]["status"] == "pass", (
        "SQLite FTS5 backs the whole index; this machine builds the index in the other "
        f"suites, so doctor must find it: {rows['fts5']['detail']!r}"
    )


def test_the_home_check_reports_the_resolved_library(home):
    write_config(home)
    _, rows = doctor(home)
    assert rows["home"]["status"] == "pass"
    assert str(home) in rows["home"]["detail"], (
        "the home check names the home it resolved, so a surprise $TAPEDECK_HOME is visible"
    )


def test_the_platform_is_judged_against_the_configured_transcriber(home):
    write_config(home, transcriber="mlx_whisper --model mlx-community/whisper-large-v3-turbo")
    _, rows = doctor(home)
    row = rows["platform"]

    assert (row["status"] == "pass") == APPLE_SILICON, (
        f"an MLX transcriber on {sys.platform}/{platform.machine()} was reported "
        f"{row['status']!r}: MLX runs on arm64 macOS and nowhere else"
    )
    if not APPLE_SILICON:
        detail = row["detail"]
        assert "Apple Silicon" in detail
        assert "transcriber_command" in detail or "config.toml" in detail, (
            "the message must point at the one config line that fixes it"
        )


def test_a_non_mlx_transcriber_leaves_the_platform_check_clean(home):
    write_config(home, transcriber="sh -c 'whisper-cpp'")
    _, rows = doctor(home)
    assert rows["platform"]["status"] == "pass", (
        "the platform check exists to catch MLX on the wrong silicon; any other "
        f"transcriber is portable: {rows['platform']['detail']!r}"
    )


def test_the_human_report_is_one_aligned_line_per_check(home):
    write_config(home, transcriber=f"{MISSING} --model large", librarian=None)
    r = run_cli(["doctor"], home)
    assert r.returncode == 1
    assert "\x1b" not in r.stdout, "piped output carries no escape sequences (SPEC-cli-005)"

    _, rows = doctor(home)
    columns = set()
    for name, row in rows.items():
        matches = [ln for ln in r.stdout.splitlines() if ln.strip().startswith(name)]
        assert len(matches) == 1, (
            f"expected exactly one report line opening with {name!r}, got {matches!r}"
        )
        line = matches[0]
        marker = re.search(rf"\b{row['status']}\b", line[line.index(name) + len(name):])
        assert marker, (
            f"the line for {name!r} does not carry its {row['status']!r} status: {line!r}"
        )
        columns.add(line.index(name) + len(name) + marker.start())
    assert len(columns) == 1, (
        f"the status begins at a different column on different lines: {sorted(columns)}"
    )


def test_doctor_resolves_the_seams_without_running_them(home):
    """`doctor` is a diagnosis, not a rehearsal: it looks names up on PATH and
    executes nothing it finds, so a broken seam can be diagnosed safely."""
    tripwire = home / "seam-was-executed"
    script = home / "fetch.sh"
    script.write_text(f'#!/bin/sh\ntouch "{tripwire}"\n')
    write_config(home, fetcher=f"sh {script}")

    config_before = (home / "config.toml").read_text()
    library_before = sorted(p.name for p in (home / "library").iterdir())

    r = run_cli(["doctor"], home)
    assert r.returncode in (0, 1)
    assert not tripwire.exists(), "doctor ran a seam command instead of resolving its head"
    assert (home / "config.toml").read_text() == config_before, (
        "doctor rewrote a config it was only asked to read"
    )
    assert sorted(p.name for p in (home / "library").iterdir()) == library_before


def test_doctor_works_on_a_home_that_does_not_exist_yet(tmp_path):
    """The first thing a stranger runs after installing, before any library work."""
    home = tmp_path / "fresh" / "deck"
    r = run_cli(["doctor", "--json"], home)
    rows = json.loads(r.stdout)
    assert [row["check"] for row in rows] == list(CHECKS)
    assert (home / "config.toml").is_file(), (
        "doctor scaffolds the home like every other verb — and diagnoses the defaults"
    )
