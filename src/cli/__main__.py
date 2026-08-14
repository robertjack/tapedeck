"""`python -m cli` — the same entrypoint the installed `tapedeck` script runs."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
