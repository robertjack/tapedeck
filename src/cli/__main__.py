"""`python -m cli` — the same entry point the `tapedeck` console script uses."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
