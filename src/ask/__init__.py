"""ask — a question in, an answer out, every claim traceable to a timestamp.

A librarian agent reads the library home and is believed only after its citations
are checked; `--fast` retrieves first and answers from the retrieval alone; `--video`
narrows either mode and the check with it (SPEC-ask-001..004). ask writes nothing.

That check is itself a boundary: `python -m ask verify` reads text on stdin and
reports whether its citations hold, so a component that must judge a page's
citations (wiki) reaches ask's verdict by asking ask rather than by keeping its own
copy of the grammar (SPEC-ask-005, LESSON-0003). One reading, two doors.

The seam defaults the cli scaffolds config.toml from live in `ask.seams`.
"""
