"""`python -m cli` — the same entrypoint the `tapedeck` console script calls."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
