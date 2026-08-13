"""`python -m cli` — the same entrypoint the installed `tapedeck` script runs."""

from __future__ import annotations

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
