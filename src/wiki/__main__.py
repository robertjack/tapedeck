"""Component boundary: `python -m wiki file|sync|lint|rebuild|tend`.

Reads `config.toml` for its one seam, the library and the archive pages to judge
what the maintainer wrote, and writes nothing outside `$TAPEDECK_HOME/wiki/`
(SPEC-core-001) — in particular not `config.toml`, which is cli's.

Exit codes follow system/contracts/cli-surface.md: 0 success, 1 operation
failure, 2 usage or config error. The division is worth stating because both
appear here for the same-looking situations. A malformed id, an id the library
does not hold, a missing seam, and a wiki that a verb about an existing wiki
cannot find are all *usage*: nothing has been attempted and nothing spent. A
missing archive page, a crashed maintainer, a rejected gate and a wiki another
operation is holding are *failures*: the request was fair and the work could not
be done. Everything a user has to act on goes to stderr; stdout carries only what
the verb was asked to produce — the rehearsal's ids, the report, the findings, the
summary.

The whole group reaches the installed tool through SPEC-cli-009's pass-through, so
this parser is the only copy of the wiki's surface that exists.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import Failure, Usage, filing, lint

DEFAULT_HOME = "~/dev/storage/tapedeck"


def home_dir() -> Path:
    return Path(os.environ.get("TAPEDECK_HOME") or DEFAULT_HOME).expanduser()


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wiki",
        description="the prose side of the library: file, sync, lint, rebuild or tend the wiki",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    filing_one = sub.add_parser("file", help="file one library video into the wiki")
    filing_one.add_argument("video_id")

    sweep = sub.add_parser("sync", help="file every library video the wiki does not know")
    sweep.add_argument(
        "--dry-run", action="store_true", help="print the ids it would file, and do nothing"
    )

    report = sub.add_parser("lint", help="diagnose the wiki; changes nothing")
    report.add_argument("--json", action="store_true", help="the same checks, as JSON")

    again = sub.add_parser("rebuild", help="empty the wiki and file the whole library again")
    again.add_argument("--yes", action="store_true", help="consent to the preview's plan")

    tending = sub.add_parser("tend", help="read the whole wiki and report; --yes to let it act")
    tending.add_argument("--yes", action="store_true", help="let the tender edit, under the gate")

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    home = home_dir()
    try:
        if args.verb == "file":
            return filing.file_video(home, args.video_id)
        if args.verb == "sync":
            return filing.sync(home, args.dry_run)
        if args.verb == "lint":
            return lint.lint(home, args.json)
        if args.verb == "rebuild":
            return filing.rebuild(home, args.yes)
        return filing.tend(home, args.yes)
    except Usage as exc:
        return _report([str(exc)], 2)
    except Failure as exc:
        return _report(exc.lines or [str(exc)], 1)
    except OSError as exc:
        return _report([str(exc)], 1)


def _report(lines: list[str], code: int) -> int:
    """Every reason, not the first: one run tells the user everything that is
    wrong rather than costing them a maintainer invocation per violation."""
    if len(lines) == 1:
        print(f"error: {lines[0]}", file=sys.stderr)
    else:
        print("error: this operation was rejected and nothing was committed:", file=sys.stderr)
        for line in lines:
            print(f"  {line}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
