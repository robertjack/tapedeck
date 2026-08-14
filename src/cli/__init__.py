"""tapedeck's entrypoint: the verbs of system/contracts/cli-surface.md.

The cli owns no knowledge of its own. It resolves `$TAPEDECK_HOME`, scaffolds a
fresh one, parses arguments, and drives the components that do the work — asking
each of them the questions they own rather than answering any itself.
"""


class Failure(Exception):
    """An operation that could not complete, carrying the exit code it means.

    The three codes of system/contracts/cli-surface.md are the whole error
    vocabulary: 0 success, 1 the operation failed, 2 the request was malformed.
    Everything raised inside the cli chooses between the last two here, so the
    choice is made where the reason is known rather than at the top of main().
    """

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code
