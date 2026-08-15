---
id: LESSON-0004
components: [wiki]
source: production
evidence: 2026-08-15 live library, first night of the wiki layer: a `tapedeck add` auto-filing epilogue ran concurrently with a `wiki sync` sweep on the same wiki. One operation's pre-run step found the other's half-written filing in the working tree and committed it as `user edits` (commit 36d06da, 1,362 machine-written lines including a complete sources/eRrc1pUY5oU.md). Every page still passed a gate before landing, but the history mislabeled a filing's work as the user's, and nothing prevented worse interleavings.
status: active
---
Wiki operations must be mutually exclusive, and the exclusion must be mechanical.
The pre-run `user edits` commit — the step that protects hand-written work — is
exactly the step that mislabels a neighbor's work-in-progress when two operations
interleave, so politeness between callers is not a fix; a lock is. It lives inside
the wiki's git directory where no rollback machinery reaches, it is advisory and
released by the operating system with the process (a crashed operation leaves
nothing to clean up), and a second mutating operation fails fast with a message
naming the situation rather than waiting or interleaving. Read-only diagnosis
stays lock-free. Callers built on best-effort filing — `add`'s epilogue above all
— treat the refusal as any other filing failure: note it and move on; the next
`sync` converges.
