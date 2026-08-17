---
id: SPEC-wiki-007
type: requirement
component: wiki
status: active
depends: [SPEC-wiki-002, SPEC-wiki-006, SPEC-core-004]
---
A maintainer run is watched, not awaited. A filing is minutes of agent work, and today
every one of them holds the terminal in silence from the moment the maintainer starts to
the moment it exits — during `tapedeck add`'s epilogue, during every `[n/m]` of a sweep,
during a tend. Silence that long reads as a hang, and the only diagnostic a user has for a
hang is Ctrl-C, which costs the rollback plus everything the run had already spent. The
run's outcome semantics do not change here at all — the exit code and the gate decide what
lands, exactly as SPEC-wiki-002 and SPEC-wiki-006 already say — what changes is that the
user can see the run happening while it happens.

**Every run announces itself.** Before the maintainer starts, one line on stderr says
which operation is beginning and what it is about — the filing names its video, a tend
names its mode. Silence before that line is tapedeck settling the cheap questions;
silence after it is the agent working, and the difference is now visible. stderr is the
channel because it is where every diagnostic this component emits already goes, and it is
the stream `add` relays live while reserving stdout for its own summary.

**The maintainer's stdout is read as it arrives**, line by line, not collected after
exit. A line that parses as a Claude Code stream event — the JSONL that
`claude -p --output-format stream-json --verbose` emits — becomes one compact progress
line on stderr, written when the event arrives rather than when the run ends; that
immediacy is the entire difference between progress and a post-mortem, and the evals
drive it with a maintainer that sleeps between events. Three kinds of event earn a line:
initialization names the model that answered; a tool use names the tool and, when its
input carries something recognizable — a file path, a pattern, a command — the thing it
touched; the result event closes the run's account. Other event kinds pass without a
line. This is progress, not a transcript: the agent's prose belongs to the pages it
writes and to tend's report, not to the feed.

**The product rule.** Streaming changes what the maintainer's stdout *is*, and must not
change what the user receives. For a run whose stdout parsed as a stream, the run's
product is the result event's text; for any other run it is the raw stdout, byte for
byte, exactly as today. So SPEC-wiki-006's guarantee — a tend report reaches the user
unedited, as prose in the maintainer's voice — holds under either kind of maintainer, and
raw JSONL never reaches stdout. Progress lines never appear on stdout either: stdout
belongs to the product, stderr to the watching.

**The seam is unchanged** (SPEC-core-004). `[wiki].maintainer_command` still holds
whatever shell command the user wants, and a maintainer that emits no parseable events
loses nothing: it gets the announce line, its stdout is kept whole, and the run behaves
exactly as it always has. The *default* command — the one the scaffold writes and the
unconfigured-seam message suggests — gains `--output-format stream-json --verbose`, so a
fresh install watches its agent work without being asked to configure anything. A user
who prefers another agent, or prefers the silence, edits one line and has it.

What this is deliberately not: a progress bar with a percentage. An agent run has no
denominator — nothing knows how many steps a filing takes until it has taken them — so
the honest display is a live feed of what the agent is doing, and the determinate counts
stay where they already are: `sync`'s `[n/m]` prefix and `add`'s end-of-sweep summary.

**Amended (SPEC-cli-011, SPEC-wiki-012):** `add`'s epilogue is no longer one of the
watched terminals — the cli detaches it, its streamed progress goes unread, and its
record is the log entry every run already writes. Everything above is unchanged
everywhere a person is present: a foreground `wiki file`, every `[n/m]` of a sweep, a
tend. And the announce discipline gains one line it did not need before: a `--wait`
filing that finds the wiki held says it is waiting before it goes silent
(SPEC-wiki-012), because that silence is otherwise indistinguishable from a hang.
