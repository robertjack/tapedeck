"""`setup` — the first verb of a new machine (SPEC-cli-008).

`doctor` names the gap; `setup` names the gap and the command that closes it
here. That is the whole difference between them, and it is why the diagnosis
below is not written here: the checks, their order, their statuses and their
reasons all come from `doctor.diagnose`, so a check added there appears in this
wizard with nothing written in this file. What is added here is the remedy — one
line under each required failure, verbatim runnable.

One hard rule: it installs nothing the user did not consent to. Without `--yes`
this prints and stops, and there is no path through it that runs anything at all.
With `--yes` the user has said yes to the commands just printed and to those
only — not to the optional seams, which are never installed however many times
you type it, and not to Homebrew, whose own installation is a deliberate step a
wizard has no business taking on someone's behalf.

The remedies are a seam like every other (SPEC-core-004): `[setup]` in
config.toml, keyed by executable name. Swapping brew for MacPorts is a line in a
config file, and `--yes` then runs that.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from . import doctor
from .home import DEFAULT_REMEDIES

STDERR_FD = 2
INDENT = "    "
BREW = "brew"
BREW_BOOTSTRAP = (
    '/bin/bash -c "$(curl -fsSL '
    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
)
# Where tapedeck publishes the transcriber it knows the weights of. The note is
# about a wait on the first `add`, so a number is only worth printing where we
# actually have one (SPEC-transcribe-002).
MODEL_SIZES = {"parakeet-mlx": "~2.4GB"}
NO_REMEDY = "tapedeck has no remedy for it — install it however you install things here"
NOT_AN_INSTALL = "no install fixes this one — the reason above is what to act on"
OPTIONAL_HEADING = (
    "Optional — the four-stage chain runs without these and setup never installs "
    "them; each line above says what its absence costs:"
)


def remedies(home: Path) -> dict:
    """The remedy table for this machine: what config.toml says, over what
    tapedeck ships. A user edits the line for the tool they install differently
    and keeps the rest; a config written before this table existed still knows
    what to do about yt-dlp."""
    settings, _ = doctor.config(home)
    section = settings.get("setup")
    table = section.get("remedy") if isinstance(section, dict) else None
    known = dict(DEFAULT_REMEDIES)
    if isinstance(table, dict):
        known.update({tool: value for tool, value in table.items() if isinstance(value, str)})
    return known


def commands(rows: list[dict], table: dict) -> list[str]:
    """The remedies for the required gaps, in report order, each one once. This
    is the list `--yes` consents to, and it is built from what was printed."""
    ordered = []
    for item in doctor.failed(rows):
        command = table.get(item["missing"] or "")
        if command and command not in ordered:
            ordered.append(command)
    return ordered


def homebrew_gate(needed: list[str]) -> bool:
    """Homebrew is the remedy behind the remedies. If any command about to be
    printed begins with `brew` and `brew` is not here, that is the first thing to
    say — and it is said above the remedies that need it, never run for anyone."""
    if not any(command.split()[:1] == [BREW] for command in needed):
        return False
    if shutil.which(BREW):
        return False
    print(
        "Homebrew is not installed, and the commands below need it. Install it "
        f"first (this is the one-liner published at https://brew.sh):\n\n{INDENT}"
        f"{BREW_BOOTSTRAP}\n"
    )
    return True


def show(home: Path, rows: list[dict], table: dict) -> None:
    """doctor's report, with the fix written under each required gap."""
    for item, line in zip(rows, doctor.report(rows).splitlines()):
        print(line)
        if item["status"] == doctor.FAIL:
            print(INDENT + fix(item, table))
    optional(rows, table)
    model_note(rows, home)


def fix(item: dict, table: dict) -> str:
    """What closes one required gap: the command, or the honest alternative."""
    tool = item["missing"]
    if not tool:
        # home, fts5, platform, and a seam left out of config.toml: real
        # failures with nothing to install (SPEC-cli-008).
        return NOT_AN_INSTALL
    return table.get(tool) or f"{tool} is missing, and {NO_REMEDY}"


def optional(rows: list[dict], table: dict) -> None:
    """The optional seams that do not resolve, apart from the required gaps:
    shown as guidance, never executed, never part of the exit code."""
    seen = {}
    for item in rows:
        tool = item["missing"]
        if item["status"] == doctor.OPTIONAL and tool and tool not in seen:
            seen[tool] = table.get(tool) or NO_REMEDY
    if not seen:
        return
    print(f"\n{OPTIONAL_HEADING}")
    width = max(len(tool) for tool in seen)
    for tool, guidance in seen.items():
        print(f"{INDENT}{tool:<{width}}  {guidance}")


def model_note(rows: list[dict], home: Path) -> None:
    """The one wait this wizard can warn about and cannot spare anybody. Nothing
    is downloaded here; a transcriber that is not installed promises no download
    at all, so the note only belongs beside one that resolved."""
    settings, _ = doctor.config(home)
    installed = [
        item
        for item in rows
        if item["check"] == ".".join(doctor.TRANSCRIBER) and item["status"] == doctor.PASS
    ]
    if not installed:
        return
    tool = doctor.head(doctor.setting(settings, *doctor.TRANSCRIBER))
    size = MODEL_SIZES.get(tool)
    weights = f"the model ({size} for {tool})" if size else "the model"
    print(
        f"\nNote: the first transcription downloads {weights} — that wait belongs "
        "to your first `tapedeck add`, not to setup."
    )


def install(needed: list[str]) -> None:
    """The consented commands, in the printed order, each one's own output
    streaming past as it happens. One that fails is reported and the rest still
    run: a machine missing two tools should end the run missing at most one."""
    for command in needed:
        print(f"\n+ {command}", file=sys.stderr)
        sys.stderr.flush()
        code = subprocess.run(command, shell=True, stdout=STDERR_FD).returncode
        if code:
            print(f"error: `{command}` exited {code}", file=sys.stderr)


def verdict(rows: list[dict], advise: bool) -> int:
    """The answer at a glance, and the exit code that agrees with it."""
    broken = doctor.failed(rows)
    if not broken:
        print("\nReady — nothing required is missing. Try: tapedeck add <url>")
        return 0
    counted = f"{len(broken)} required {'check' if len(broken) == 1 else 'checks'}"
    if advise:
        print(f"\n{counted} failed. Run what is printed above, or `tapedeck setup --yes`.")
    else:
        print(f"\n{counted} still failing.")
    return 1


def run(home: Path, yes: bool) -> int:
    """Scaffold, say where, check, print — and only then, and only with `--yes`,
    run what was printed and check again."""
    print(f"Library home: {home}\n")  # main scaffolded it; this makes it visible
    rows = doctor.diagnose(home)
    table = remedies(home)
    needed = commands(rows, table)
    blocked = homebrew_gate(needed)
    show(home, rows, table)

    if not yes:
        return verdict(rows, advise=True)
    if blocked:
        print("\nNothing was run: Homebrew comes first, and that step is yours.")
        return 1
    install(needed)
    # Look again from scratch: a remedy may have changed config.toml as well as
    # PATH, so nothing about the first pass is reused (SPEC-cli-008).
    rows = doctor.diagnose(home)
    print()
    show(home, rows, remedies(home))
    return verdict(rows, advise=False)
