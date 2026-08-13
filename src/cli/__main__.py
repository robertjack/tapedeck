"""`python -m cli` — the same entry point the `tapedeck` script installs."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
