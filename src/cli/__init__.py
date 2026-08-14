"""cli — the `tapedeck` executable: the one surface a person types at.

Sole writer of `$TAPEDECK_HOME/config.toml` (system/contracts/library-layout.md)
and the sole authority on where the home is (SPEC-cli-001). Everything else it
does is orchestration: each verb drives the component that owns the work through
that component's module CLI, in the order of the derivation chain.

The exit codes are the contract's (system/contracts/cli-surface.md) and they are
named here because every module in the package raises against them.
"""

SUCCESS = 0
FAILURE = 1  # the operation was understood and did not succeed
USAGE = 2  # the request was malformed, or names something that is not here


class Failure(Exception):
    """An operation that could not complete; carries the process exit code.

    A component we drove has already said what went wrong on its own stderr, so
    the message here says which video or which verb it happened to — never a
    second translation of the child's error.
    """

    def __init__(self, message, code=FAILURE):
        super().__init__(message)
        self.code = code


__all__ = ["FAILURE", "SUCCESS", "USAGE", "Failure"]
