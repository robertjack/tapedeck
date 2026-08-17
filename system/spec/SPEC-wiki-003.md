---
id: SPEC-wiki-003
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-core-003]
---
`sync [--dry-run]` files every library video the wiki does not yet know about. `file <id>`
is the unit of work and this is the verb that reaches the whole library with it: the user
who has added forty videos since the last filing should not have to remember which forty,
nor write the loop themselves. It resolves the library home and the wiki exactly as `file`
does, and it adds nothing to the installed `tapedeck` surface this round — the boundary it
appears on is `python -m wiki`.

The sweep selects only what it could actually file, which is **the retranscribe sweep's
discipline** (SPEC-cli-004) applied to a different layer, and it is quoted here
deliberately rather than reinvented: a directory under `library/` whose name is a
well-formed video id by ingest's grammar, whose media is present by ingest's rule, and
whose `archive/<id>.md` exists — the three preconditions `file` itself checks, hoisted to
the front so the sweep never starts an operation it knows will fail. The archive page is
the maintainer's reading material; a video without one has nothing to file *from*.
Everything else under `library/` — a directory that is not an id, an entry whose video was
reclaimed by `rm --media-only`, an entry not yet rendered — gets a skip note on stderr and
is left untouched. That is what makes convergence reachable: once the videos the sweep can
file are filed, the next `sync` is a no-op, however many unfilable or media-less entries the
library keeps.

Eligible and carrying no `wiki/sources/<id>.md` is **unfiled**, and unfiled is the whole
selection rule. There is no queue, no manifest, no last-synced marker: the filed-state
marker is the source page's existence (SPEC-wiki-001), so the question "what is left" is
answered by the filesystem and cannot disagree with itself. A user who deletes a source
page has asked for that video to be filed again, and the next `sync` obliges without being
told.

Each unfiled video is filed **through the same operation as `file <id>`** — the same
maintainer seam, the same acceptance gate over the whole wiki, the same `user edits`
pre-run commit, one commit per accepted filing and one rollback per rejected one. `sync` is
a loop around that operation and not a second implementation of it, because a sweep that
verified less than the single verb would be a way to get unreviewed prose into the wiki by
asking for more of it at once. Per-video commits are what keep the history legible after a
sweep of forty: the wiki's memory should read as forty filings, each revertible on its own,
not as one undivided blob.

The order is **`upload_date` ascending from each video's `meta.json`, ties broken by id**.
The wiki is path-dependent by design (SPEC-wiki-001) — the maintainer writes against what
is already there, so a page filed early is context for every page filed after it — which
means the sweep's order is not a detail but a choice about the artifact it produces. Filing
in upload order makes the wiki accumulate in the order the material appeared: a channel's
argument develops forward, a later video's page can refer back to the earlier one it
answers, and a sweep of a backlog reads the same way a viewer who had been watching all
along would have written it. The tiebreak on id exists so the order never falls through to
whatever order the filesystem happened to return; the same library filed twice produces the
same sequence.

One video's failure never stops the sweep. A rejected gate, a crashed maintainer, an
unreadable `meta.json` — each is reported on stderr, its own operation is rolled back by
`file`'s own rules, and the sweep moves to the next video, because the alternative is a
sweep whose result depends on where in the alphabet the first bad video sat. It ends with a
one-line summary counting what was filed, what was already filed, what was skipped, and
what failed — naming those outcomes in those words, `filed`, `already filed`, `skipped`,
`failed`, so the line reads the same on every machine and greps the same in every script —
and exits 0 when nothing failed and 1 otherwise — the same shape `retranscribe` uses, for
the same reason: the count is the thing the user came back to read.

A fully-filed library is a no-op that exits 0 **without invoking the maintainer at all**.
Idempotence is SPEC-core-003's rule for every verb, and here it also has a price attached:
the maintainer is an agent that costs time and money to run, and a sync that re-ran it on
already-filed videos would make re-running the verb something the user has to think about.

`--dry-run` answers "what would this do" without doing any of it. It prints the ids it
would file, one per line on stdout, in sweep order and nothing else, so the rehearsal is a
list a user can read or pipe rather than a paragraph they have to parse; the skip notes go
to stderr as they do on a real sweep. It changes nothing whatsoever — in particular it does
not scaffold a wiki that is absent, since creating a repository is not "nothing", and the
user asking what a sweep would do has not asked for one to exist. It never reads the
maintainer seam, so it is answerable on a machine where no agent is configured; a real
`sync` with the seam missing or empty exits 2 naming the key, exactly as `file` does.
