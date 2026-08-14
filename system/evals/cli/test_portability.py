"""Durable evals: the tool on a machine that is not its author's.

SPEC-cli-001 (the default library home is `~/Tapedeck` — a visible directory in
whoever's home, not a path from the author's disk) and SPEC-cli-006 (`--version`
answers from package metadata, before any library work).

Boundary: the `tapedeck` executable. The default-home test cannot use
`conftest.run_cli`, which always pins `$TAPEDECK_HOME`; it runs its own
subprocess with that variable stripped and `$HOME` pointed at a tmp dir, so a
mistake scaffolds inside tmp and never on the real disk.
"""

import os
import re
import shlex
import subprocess
import tomllib

from conftest import REPO, TIMEOUT, run_cli

SEMVER = re.compile(r"^\d+\.\d+\.\d+")


def run_cli_homeless(args, fake_home):
    """The executable as a stranger runs it: no $TAPEDECK_HOME at all."""
    cmd = os.environ.get("TAPEDECK_BIN", "tapedeck")
    env = {k: v for k, v in os.environ.items() if k != "TAPEDECK_HOME"}
    env["HOME"] = str(fake_home)
    return subprocess.run(
        [*shlex.split(cmd), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env=env,
    )


def pyproject_version():
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_default_home_is_a_visible_dir_in_the_users_home(tmp_path):
    fake_home = tmp_path / "someone-else"
    fake_home.mkdir()

    r = run_cli_homeless(["list"], fake_home)
    assert r.returncode == 0, r.stderr

    deck = fake_home / "Tapedeck"
    assert deck.is_dir(), (
        f"with $TAPEDECK_HOME unset the default home is ~/Tapedeck; "
        f"$HOME holds only {sorted(p.name for p in fake_home.iterdir())}"
    )
    assert (deck / "library").is_dir(), "first use scaffolds the home (SPEC-cli-001)"
    assert (deck / "config.toml").is_file(), "first use writes config.toml"


def test_default_home_carries_no_path_from_the_authors_machine(tmp_path):
    fake_home = tmp_path / "someone-else"
    fake_home.mkdir()

    assert run_cli_homeless(["list"], fake_home).returncode == 0
    assert not (fake_home / "dev").exists(), (
        "the default home must not be a path particular to one machine "
        "(~/dev/storage/tapedeck was the author's)"
    )
    assert not (fake_home / "Library" / "tapedeck").exists(), (
        "the archive pages are meant to be browsed, so the default is not hidden away"
    )


def test_version_prints_a_version_and_exits_0(home):
    r = run_cli(["--version"], home)
    assert r.returncode == 0, r.stderr
    printed = r.stdout.strip()
    assert printed, "--version prints to stdout"
    assert SEMVER.match(printed.split()[-1]), f"not a version string: {printed!r}"


def test_version_is_the_packaged_version(home):
    r = run_cli(["--version"], home)
    assert r.returncode == 0, r.stderr
    assert pyproject_version() in r.stdout, (
        f"--version reports {r.stdout.strip()!r}; the distribution's metadata says "
        f"{pyproject_version()!r} — the version has one source of truth (SPEC-cli-006)"
    )


def test_version_needs_no_library_home(tmp_path):
    fake_home = tmp_path / "brand-new"
    fake_home.mkdir()

    r = run_cli_homeless(["--version"], fake_home)
    assert r.returncode == 0, r.stderr
    assert pyproject_version() in r.stdout
    assert not (fake_home / "Tapedeck").exists(), (
        "--version is answered before any library work: it scaffolds nothing"
    )


def test_manual_documents_the_version_flag():
    manual = (REPO / "MANUAL.md").read_text(encoding="utf-8")
    assert "--version" in manual, "MANUAL.md must document the --version option"


def test_manual_carries_no_stale_default_home():
    manual = (REPO / "MANUAL.md").read_text(encoding="utf-8")
    assert "dev/storage/tapedeck" not in manual, (
        "MANUAL.md still names the author's old default library home"
    )
    assert "~/Tapedeck" in manual, "MANUAL.md must name the default home"


def test_the_tour_names_the_current_default_home(home):
    r = run_cli(["help"], home)
    assert r.returncode == 0, r.stderr
    assert "dev/storage/tapedeck" not in r.stdout, (
        "the tour still names the author's old default library home"
    )
