"""Durable evals: `tapedeck setup`, the first-run wizard (SPEC-cli-008).

Boundary: the `tapedeck` executable, library via $TAPEDECK_HOME.

Nothing here may install anything, so every fixture overrides the whole remedy
table through the `[setup]` seam the clause publishes: `remedy.<executable>`.
The shipped brew/uv defaults are asserted separately, by reading the config a
fresh home is scaffolded with — read, never run. A fixture remedy is a shell
script that touches a marker file, which makes "was this executed?" a question
the filesystem answers rather than the output.

`sh` stands in for "a command that resolves"; MISSING for one that cannot.
"""

import json
import shlex
import shutil
import tomllib

import pytest

from conftest import run_cli

MISSING = "tapedeck-no-such-tool-2f9c1a"
REQUIRED_SEAMS = (
    "ingest.fetcher_command",
    "ingest.lister_command",
    "transcribe.transcriber_command",
)


def script(home, name, body):
    """A remedy the eval can prove ran, without installing anything."""
    path = home / name
    path.write_text("#!/bin/sh\n" + body)
    return f"sh {path}"


def write_config(
    home,
    *,
    fetcher="sh -c :",
    lister="sh -c :",
    transcriber="sh -c :",
    librarian="sh -c :",
    answerer="sh -c :",
    remedies=(),
):
    """A config.toml with the seams pointed wherever this test needs them and a
    remedy table that can never reach a package manager. `remedies` is
    (executable, command) pairs; every fixture also neutralises the remedy for
    `ffmpeg`, so a host that genuinely lacks it still cannot trigger a real
    `brew install` under --yes."""
    lines = [
        "[ingest]",
        f'fetcher_command = "{fetcher}"',
        f'lister_command = "{lister}"',
        "",
        "[transcribe]",
        f'transcriber_command = "{transcriber}"',
        'model = "fixture/whisper-0"',
        "",
        "[ask]",
        f'librarian_command = "{librarian}"',
        f'answerer_command = "{answerer}"',
        "",
        "[setup]",
        f'remedy.ffmpeg = "{script(home, "remedy-ffmpeg.sh", ": # a fixture never installs")}"',
    ]
    for tool, command in remedies:
        lines.append(f'remedy.{tool} = "{command}"')
    (home / "config.toml").write_text("\n".join(lines) + "\n")


def needs_ffmpeg():
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is genuinely absent here, so a required check would rightly fail")


def doctor_rows(home):
    r = run_cli(["doctor", "--json"], home)
    return {row["check"]: row for row in json.loads(r.stdout)}


def lines_for(stdout, check):
    return [ln for ln in stdout.splitlines() if check in ln]


def test_a_healthy_install_is_ready_and_exits_0(home):
    needs_ffmpeg()
    write_config(home)
    r = run_cli(["setup"], home)
    assert r.returncode == 0, f"nothing required is missing here:\n{r.stdout}\n{r.stderr}"
    assert "ready" in r.stdout.lower(), (
        f"the healthy answer must be legible at a glance: {r.stdout!r}"
    )
    assert "\x1b" not in r.stdout, "piped output carries no escape sequences (SPEC-cli-005)"


def test_setup_scaffolds_the_home_and_says_where_it_is(tmp_path):
    """The first command of a new machine, run before there is a library."""
    home = tmp_path / "fresh" / "deck"
    r = run_cli(["setup"], home)
    assert r.returncode in (0, 1)
    assert (home / "config.toml").is_file(), "setup performs the first-run scaffold"
    assert (home / "library").is_dir() and (home / "archive").is_dir()
    assert str(home) in r.stdout, (
        "setup names the home it resolved, so a surprising $TAPEDECK_HOME is visible "
        f"before anything else is discussed: {r.stdout!r}"
    )


def test_setup_reports_exactly_what_doctor_reports(home):
    """One implementation, two verbs. Layout may differ; the diagnosis may not."""
    write_config(home, transcriber=f"{MISSING} --model large", librarian=f"{MISSING}-agent -p")
    rows = doctor_rows(home)
    r = run_cli(["setup"], home)

    for check, row in rows.items():
        matches = lines_for(r.stdout, check)
        assert matches, f"setup dropped a check doctor reports: {check!r}\n{r.stdout}"
        assert any(row["status"] in ln for ln in matches), (
            f"setup disagrees with doctor about {check!r}: doctor says {row['status']!r}, "
            f"setup printed {matches!r}"
        )


def test_a_missing_required_tool_prints_its_remedy_and_runs_nothing(home):
    """Consent is the spec: without --yes, setup executes nothing whatsoever."""
    marker = home / "remedy-ran"
    remedy = script(home, "remedy.sh", f'touch "{marker}"\n')
    write_config(home, transcriber=f"{MISSING} --model large", remedies=[(MISSING, remedy)])

    r = run_cli(["setup"], home)
    assert r.returncode == 1, "a required tool that is missing is exit 1"
    assert remedy in r.stdout, (
        f"the exact remedy command must be printed, verbatim runnable: {r.stdout!r}"
    )
    assert not marker.exists(), "setup ran a remedy without --yes"


def test_a_missing_transcriber_carries_no_model_download_note(home):
    """The note is about a wait the user will meet; a tool that isn't there
    promises no download, and the remedy comes first."""
    write_config(home, transcriber=f"{MISSING} --model large")
    r = run_cli(["setup"], home)
    assert r.returncode == 1
    assert MISSING in r.stdout, f"the missing transcriber is named: {r.stdout!r}"
    assert "first transcription" not in r.stdout.lower(), (
        f"nothing will be downloaded by a transcriber that is not installed: {r.stdout!r}"
    )


def test_an_installed_transcriber_warns_about_the_first_download(home):
    needs_ffmpeg()
    write_config(home)
    r = run_cli(["setup"], home)
    note = [ln for ln in r.stdout.splitlines() if "first transcription" in ln.lower()]
    assert note, (
        "with the transcriber present, setup says the first transcription downloads the "
        f"model — the one thing that will take a while later: {r.stdout!r}"
    )
    assert any("download" in ln.lower() for ln in note), note


def test_yes_runs_the_remedy_and_checks_again(home):
    """--yes is consent to the printed commands: they run, and then setup looks
    again — re-reading config.toml, because a remedy may have changed it."""
    needs_ffmpeg()
    marker = home / "remedy-ran"
    fixed = home / "fixed-config.toml"
    remedy = script(home, "remedy.sh", f'touch "{marker}"\ncp "{fixed}" "{home}/config.toml"\n')

    write_config(home, transcriber=f"{MISSING} --model large", remedies=[(MISSING, remedy)])
    # what the remedy leaves behind: the same config with a transcriber that resolves
    fixed.write_text(
        (home / "config.toml").read_text().replace(f"{MISSING} --model large", "sh -c :")
    )

    r = run_cli(["setup", "--yes"], home)
    assert marker.exists(), f"--yes did not run the remedy it printed:\n{r.stdout}\n{r.stderr}"

    seen = lines_for(r.stdout, "transcribe.transcriber_command")
    assert len(seen) == 2, (
        f"the report is printed twice: once before the remedies, once after: {seen!r}"
    )
    assert "fail" in seen[0], seen
    assert "pass" in seen[1], (
        f"the second pass must re-read config.toml, not replay the first: {seen!r}"
    )
    assert r.returncode == 0, (
        f"the exit code follows the second report, and by then nothing is missing:\n{r.stdout}"
    )


def test_an_optional_ask_seam_is_never_installed_even_with_yes(home):
    """`ask` needs the librarian and `search` never does. Optional means printed,
    pointed at, and left alone."""
    needs_ffmpeg()
    marker = home / "ask-remedy-ran"
    remedy = script(home, "ask-remedy.sh", f'touch "{marker}"\n')
    write_config(
        home,
        librarian=f"{MISSING}-agent -p",
        answerer=f"{MISSING}-agent -p",
        remedies=[(f"{MISSING}-agent", remedy)],
    )

    r = run_cli(["setup", "--yes"], home)
    assert not marker.exists(), "an optional seam's remedy is guidance, never executed"
    assert r.returncode == 0, (
        f"an unresolvable [ask] seam never decides the exit code:\n{r.stdout}"
    )


def test_setup_never_runs_a_seam_command(home):
    """Like doctor: names are resolved on PATH, not executed. Under --yes the
    only thing that runs is a remedy."""
    needs_ffmpeg()
    tripwire = home / "seam-was-executed"
    fetcher = script(home, "fetch.sh", f'touch "{tripwire}"\n')
    write_config(home, fetcher=fetcher)

    for args in (["setup"], ["setup", "--yes"]):
        r = run_cli(args, home)
        assert not tripwire.exists(), f"`tapedeck {' '.join(args)}` executed a seam command"
        assert r.returncode == 0, r.stdout


def test_a_brew_remedy_is_led_by_the_bootstrap_line_only_when_brew_is_missing(home):
    """Homebrew is the remedy behind the remedies. Never run here: a `brew`
    remedy is printed and, without --yes, that is all that can happen."""
    write_config(
        home,
        transcriber=f"{MISSING} --model large",
        remedies=[(MISSING, f"brew install {MISSING}")],
    )
    r = run_cli(["setup"], home)
    assert r.returncode == 1
    said_so = "homebrew" in (r.stdout + r.stderr).lower()

    if shutil.which("brew") is None:
        assert said_so, (
            "every brew remedy needs brew: say that first, with the bootstrap one-liner "
            f"— otherwise the printed command cannot be run:\n{r.stdout}"
        )
    else:
        assert not said_so, (
            f"brew is here; telling the user to install it is noise:\n{r.stdout}"
        )


def test_the_shipped_remedies_are_published_in_the_scaffolded_config(tmp_path):
    """The eval injects fixture remedies through this seam; what ships is
    macOS-native. Every executable the shipped defaults name has an entry, so a
    fresh install can always be told what to do next."""
    home = tmp_path / "shipped"
    run_cli(["doctor", "--json"], home)  # any verb scaffolds; this one changes nothing else
    config = tomllib.loads((home / "config.toml").read_text())

    remedy = config.get("setup", {}).get("remedy")
    assert isinstance(remedy, dict) and remedy, (
        f"the remedy table is published like every other seam default: {config.get('setup')!r}"
    )
    assert remedy.get("yt-dlp") == "brew install yt-dlp"
    assert remedy.get("ffmpeg") == "brew install ffmpeg"
    assert remedy.get("mlx_whisper", "").startswith("uv tool install"), remedy
    assert remedy.get("parakeet-mlx", "").startswith("uv tool install"), (
        "the published parakeet alternative is installable too (SPEC-transcribe-002)"
    )
    assert "claude" in remedy.get("claude", "").lower(), (
        f"the optional ask seams point at installing claude: {remedy.get('claude')!r}"
    )

    heads = {"ffmpeg"}
    for section in ("ingest", "transcribe", "ask", "wiki"):
        for key, value in config.get(section, {}).items():
            if key.endswith("_command"):
                heads.add(shlex.split(value)[0])
    missing = sorted(head for head in heads if head not in remedy)
    assert not missing, f"shipped defaults name tools the shipped remedy table cannot fix: {missing}"


# --- setup --refresh: update what exists, never install what doesn't (SPEC-cli-013)


def add_updates(home, *pairs):
    """Update rows through the same `[setup]` seam the remedies use. write_config
    leaves the file inside its [setup] section, so appending keeps the table."""
    with (home / "config.toml").open("a") as fh:
        for tool, command in pairs:
            fh.write(f'update.{tool} = "{command}"\n')


def test_refresh_prints_the_update_and_runs_nothing_without_yes(home):
    needs_ffmpeg()
    write_config(home)
    marker = home / "updated-ffmpeg"
    add_updates(home, ("ffmpeg", script(home, "update-ffmpeg.sh", f"touch {marker}")))
    r = run_cli(["setup", "--refresh"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert lines_for(r.stdout, "update-ffmpeg.sh"), (
        f"--refresh names the update command for a tool that resolves:\n{r.stdout!r}"
    )
    assert not marker.exists(), "printing is all --refresh does without --yes"


def test_refresh_yes_runs_exactly_the_printed_updates(home):
    needs_ffmpeg()
    write_config(home)
    marker = home / "updated-ffmpeg"
    add_updates(home, ("ffmpeg", script(home, "update-ffmpeg.sh", f"touch {marker}")))
    r = run_cli(["setup", "--refresh", "--yes"], home)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert marker.exists(), "--refresh --yes runs the update it printed"


def test_refresh_never_touches_a_missing_tool(home):
    """--refresh updates what exists; installing what doesn't is the plain
    wizard's business, so a missing tool's update command must not run."""
    needs_ffmpeg()
    write_config(home, transcriber=f"{MISSING} run")
    marker = home / "updated-missing"
    add_updates(home, (MISSING, script(home, "update-missing.sh", f"touch {marker}")))
    run_cli(["setup", "--refresh", "--yes"], home)
    assert not marker.exists(), (
        "a tool that does not resolve is not the refresher's to touch"
    )


def test_the_shipped_update_table_is_scaffolded(tmp_path):
    """Like the remedies: what ships is macOS-native and written into the
    scaffolded config, one default, the code agreeing with what it wrote."""
    home = tmp_path / "shipped"
    run_cli(["doctor", "--json"], home)
    config = tomllib.loads((home / "config.toml").read_text())
    update = config.get("setup", {}).get("update")
    assert isinstance(update, dict) and update, (
        f"the update table is published beside the remedies: {config.get('setup')!r}"
    )
    assert update.get("yt-dlp") == "brew upgrade yt-dlp"
    assert update.get("ffmpeg") == "brew upgrade ffmpeg"
    assert update.get("mlx_whisper", "").startswith("uv tool upgrade"), update
    assert update.get("parakeet-mlx", "").startswith("uv tool upgrade"), update
