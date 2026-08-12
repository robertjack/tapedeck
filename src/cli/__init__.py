"""The tapedeck command line (SPEC-cli-001).

The entrypoint owns three things and delegates everything else: which verbs
exist, where the library is, and the order the derivation chain runs in.
"""

from __future__ import annotations


class Failure(Exception):
    """An operation that could not complete; carries the process exit code.

    Lives here rather than in a module so home, library and the verbs can all
    raise the one thing main knows how to turn into an exit status.
    """

    def __init__(self, message, code: int = 1):
        super().__init__(message)
        self.code = code
