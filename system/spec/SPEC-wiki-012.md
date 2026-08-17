---
id: SPEC-wiki-012
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-wiki-003, SPEC-wiki-007, SPEC-wiki-008, SPEC-wiki-011]
---
A filing may wait for the wiki instead of being refused. `file` gains `--wait`: invoked
with it against a held wiki, the filing blocks until the holder commits or rolls back,
takes the lock, and only then begins — and from that moment it is any filing at all,
alone in the wiki, judged by the gate, recorded in the log. Without the flag nothing
changes anywhere: a second operation still refuses at once with the existing message,
because an interactive caller watching a refusal can decide for themselves, and
refuse-fast stays the default this component ships.

**Waiting is not interleaving.** The lock's refusal was written against LESSON-0004,
and the incident that lesson records is two operations' *commits* braided into each
other — work from both in flight at once. A caller that blocks before its first read
has braided nothing: when it finally holds the lock, the wiki is exactly one committed
or rolled-back state, the same state a `sync` typed a minute later would find. What
refuse-fast actually costs is that the refused filing is *dropped*: today a second
`add`'s epilogue arriving mid-filing skips, the video stays unfiled, and nothing files
it until a person remembers `sync`. For a caller nobody will re-run — a fire-and-forget
epilogue (SPEC-cli-011) — the honest behaviors are wait or strand, and this flag is
wait. The wait has no deadline of its own: any deadline is a guess about how long a
neighbor's maintainer thinks, and a wait that gives up on a guess re-creates the
stranding it exists to remove. The holder is bounded by its own run; the waiter is
bounded by the holder.

**A wait announces itself.** Before blocking, one line on stderr says the wiki is held
and this filing is **waiting** for it — SPEC-wiki-007's announce discipline extended to
the one new silence this flag introduces. A `--wait` filing that finds the wiki free
prints no such line and behaves exactly as if the flag were absent.

The flag belongs to `file` alone. `sync`, `rebuild` and `tend` still refuse a held
wiki: a sweep is cheap to re-run and idempotent by design, a rebuild and a tend are
deliberate acts whose operator is present, and none of them is ever fired and
forgotten. The read-only verbs still take no lock at all. Gate, rollback, commit and
log-entry semantics are untouched — SPEC-wiki-002, SPEC-wiki-008 and SPEC-wiki-011
already say everything a waited filing does once it holds the wiki, and this clause
adds nothing after the moment the lock is acquired.
