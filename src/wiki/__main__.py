"""Component boundary: `python -m wiki file <id> | sync [--dry-run] |
lint [--json] | rebuild [--yes]`.

The library and the wiki are resolved from `$TAPEDECK_HOME` and every verb
resolves them the same way. Exit codes follow the rest of tapedeck: 0 success, 1
an operation that was attempted and did not complete, 2 a mistake in the asking
or a seam that is not configured. Reports go to stdout; skips, progress and every
violation go to stderr.

The four verbs are one operation and three shapes of it. `file` is the unit of
work; `sync` is that unit reaching the whole library; `rebuild` is the same sweep
preceded by a deliberate reset; and `lint` is the gate's questions asked of a
wiki nobody just wrote, with nothing written back.
"""

from __future__ import annotations

import argparse
import sys

from . import Failure, Usage, filing, lint
from .layout import home_dir


def parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="wiki", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)

    one = sub.add_parser("file", help="file one library video into the wiki")
    one.add_argument("video_id")

    every = sub.add_parser("sync", help="file every library video the wiki does not know")
    every.add_argument(
        "--dry-run", action="store_true", help="list what would be filed, and do none of it"
    )

    check = sub.add_parser("lint", help="diagnose the wiki and change nothing")
    check.add_argument(
        "--json", action="store_true", dest="as_json", help="the same checks, as JSON"
    )

    again = sub.add_parser("rebuild", help="empty the wiki and file the library into it again")
    again.add_argument(
        "--yes", action="store_true", help="do it; without this the command only previews"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    home = home_dir()
    try:
        if args.verb == "file":
            return filing.file_verb(home, args.video_id)
        if args.verb == "sync":
            return filing.sync(home, args.dry_run)
        if args.verb == "lint":
            return lint.run(home, args.as_json)
        return filing.rebuild(home, args.yes)
    except Usage as exc:
        return _report(exc, 2)
    except (Failure, OSError) as exc:
        return _report(exc, 1)


def _report(exc: Exception, code: int) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
