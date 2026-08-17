---
id: SPEC-cli-011
type: requirement
component: cli
status: active
depends: [SPEC-cli-003, SPEC-cli-009, SPEC-wiki-002, SPEC-wiki-012]
---
`add` returns when the library is built; the filings continue without it. Today the
epilogue holds the terminal for the whole maintainer run — ten-plus minutes of agent
work per video, after the minute or two of download, transcription and indexing the
user actually asked `add` for — and a second `add` typed during that hold finds the
wiki locked and strands its video for a later `sync` someone has to remember. After
this clause, `add`'s own work ends where the index's does: each video that completes
the four-stage chain is handed to a detached filing worker, and `add` moves on — to
the next video, then to its summary and its exit code.

**The hand-off, pinned:**

- **One worker per `add` invocation**, filing the videos the sweep completed in the
  order it completed them. SPEC-cli-009's reason for filing as each video lands — a
  filing may read pages filed earlier in the same sweep — survives detachment because
  the worker is one and its order is the sweep's, not a race of siblings on the lock.
- **The worker outlives `add` and holds none of its streams.** stdout and stderr are
  released at hand-off, not inherited: a worker holding `add`'s pipes keeps every
  reader of those pipes waiting until the last filing ends, which is `add` not
  returning, with extra steps. The worker's own diagnostics are nobody's terminal;
  its record is the wiki's log, where every run already writes one (SPEC-wiki-008,
  SPEC-wiki-011).
- **Each filing is `wiki file --wait <id>`** at the component boundary
  (SPEC-wiki-012): when a neighbor holds the wiki — another `add`'s worker, a
  foreground sync — the filing waits its turn instead of skipping, and no video is
  stranded for a person to remember. The epilogue remains a call, not a second filing
  path (LESSON-0003): maintainer, gate, rollback, idempotent skip are all the wiki's.
  The worker's stderr — the filings' live progress and any rejection's account — is
  discarded with the terminal that is not there to read it.
- **What `add` already knows, it still says, synchronously.** `[wiki].auto` false
  means `add` never touches the wiki and spawns nothing; a missing
  `[wiki].maintainer_command` is one live stderr note naming the seam, exactly as
  SPEC-cli-009 pins it — both are questions `add` answers without running anything,
  so nothing about them detaches.
- **The hand-off is announced.** When at least one video was handed to the worker,
  `add` prints one stderr line per invocation saying the wiki filings continue on
  their own, that an accepted filing lands as an entry in the wiki's **log**, and
  that `wiki sync` converges anything that does not land — so the silence after exit
  is explained before it starts. Nothing about the epilogue reaches stdout, exactly
  as before: `add`'s stdout and its summary still mean what they meant when there
  was no wiki.

**A failure after hand-off leaves what a failed filing always left.** Best-effort
stands whole: nothing the worker does — a rejected gate, a crashed maintainer, a
wait that outlives the machine — changes an exit code `add` has already returned,
and the library the pipeline built is already on disk. The wiki's own semantics are
deliberately untouched: a rejected run makes no commit and no chronology entry
(SPEC-wiki-002, SPEC-wiki-011 — its account goes to the stderr of whoever ran it,
which for the worker is no one), so the failure's durable trace is the one the
system has always had — an unfiled video. `wiki sync --dry-run` names it,
`wiki sync` converges it, and a failure worth diagnosing is reproduced by running
`wiki file <id>` in the foreground, where SPEC-wiki-007 shows it happening live.
The epilogue adds no second chronology and no failure ledger of its own: inventing
one would put a copy of the wiki's history outside the wiki (LESSON-0003), to
answer a question `sync --dry-run` already answers.

**What this deliberately is not: a queue with state.** No file lists pending filings
and nothing replays them after a crash — a worker that dies leaves videos unfiled,
which is exactly the state `sync` already converges, idempotently, on any later run.
The crash story does not change; only who does the waiting does. `doctor`, `setup`,
`rm` and every other verb on the surface are untouched, and `MANUAL.md`'s add and
wiki sections say what now happens after `add` returns.
