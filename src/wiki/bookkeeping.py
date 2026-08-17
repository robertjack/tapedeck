"""SPEC-wiki-008: the catalog and the chronology are tapedeck's, not the agent's.

Both used to be an obligation the gate could reject a run for neglecting, and
both are actually bookkeeping: which pages need a catalog line is a directory
listing, and the date and the operation name on a chronology entry are tapedeck's
own to begin with. Measured on a real wiki, paying an agent to re-read a 97KB
chronology just to append one line to it cost ~24,000 input tokens a filing and
bought nothing a machine could not already know.

So this module reconciles both **after the maintainer exits and before the gate
judges the result** (`filing.perform`) — the order matters, since a rejection has
to roll this back along with everything else the run did, and the gate must judge
the state that is actually about to be committed.

Neither reconciliation regenerates a file. The catalog is appended to — grouping,
ordering and annotation stay the brief's business (system/contracts/wiki-layout.md)
— and the chronology gains exactly one entry, and only when the maintainer's own
run did not already leave a well-formed one: a maintainer already writing its own
entries is not doing anything wrong, and two entries for one operation would be a
worse record than the one this module exists to guarantee.

**Amended again 2026-08-17.** The first version of this module made the *subject*
the maintainer's product too, and a run that narrated several sentences before its
first period swallowed all of it into the heading — `## [...] file | Filed.
Here's what landed. **sources/whcfSGN6CAU.md**`, on the user's own wiki. The
subject is tapedeck's own from here on — the video id for a filing, a short fixed
label for an operation with no single video (`filing.perform`'s caller decides
which) — and the maintainer's product, whatever it said, is the body beneath the
heading, entire and unedited. The cost figures, when the maintainer streamed them,
are written as a sentence rather than a status line: this is a chronology, and its
one piece of leaked telemetry was the first thing in it that did not read as
prose.
"""

from __future__ import annotations

from pathlib import Path

from . import layout


def reconcile_catalog(wiki: Path) -> None:
    """Append a line for every page `index.md` does not already mention."""
    index = wiki / layout.INDEX
    text = layout.read(index)
    known = set(layout.catalog(text))
    missing = [
        page
        for page in layout.pages(wiki)
        if not layout.is_pinned(wiki, page) and layout.name(wiki, page) not in known
    ]
    if not missing:
        return
    addition = "".join(f"{_catalog_line(wiki, page)}\n" for page in missing)
    sep = "" if not text or text.endswith("\n") else "\n"
    index.write_text(text + sep + addition, encoding="utf-8")


def _catalog_line(wiki: Path, page: Path) -> str:
    where = layout.name(wiki, page)
    heading = layout.opening_heading(layout.read(page))
    return f"- [{heading or where}]({where})"


def cost_sentence(cost: dict) -> str | None:
    """What the run cost, read as prose rather than a status line — the
    chronology is careful sentences everywhere else, and a figure dropped in
    unremarked reads like a tool talking to itself. Exported so a discarded run
    (`filing.read_only`) can print the same sentence a chronology entry would
    have used, without persisting one.

    Nothing is invented: a maintainer that streamed no cost contributes no
    sentence at all, never a row of zeroes standing in for a figure nobody
    measured. `total_input_tokens` is already the run's whole input, summed by
    the seam that read the stream — written here as that one total, never as the
    raw `usage.input_tokens` remainder that the pre-amendment entry reported and
    that understated a real run's cost by four orders of magnitude.
    """
    if not cost:
        return None
    clauses = []
    if "duration_s" in cost:
        clauses.append(f"took {cost['duration_s']}s")
    if "model" in cost:
        clauses.append(f"used {cost['model']}")
    total = cost.get("total_input_tokens")
    output = cost.get("output_tokens")
    if total is not None or output is not None:
        reading = None
        if total is not None:
            cached = cost.get("cache_read_tokens")
            reading = f"read {total} tokens" + (
                f" ({cached} from cache)" if cached is not None else ""
            )
        writing = f"wrote {output} tokens" if output is not None else None
        clauses.append(", ".join(part for part in (reading, writing) if part))
    if "cost_usd" in cost:
        clauses.append(f"cost ${cost['cost_usd']:.2f}")
    return f"This run {'; '.join(clauses)}." if clauses else None


def reconcile_log(
    wiki: Path,
    before_log: bytes,
    op: str,
    subject: str,
    product: str,
    cost: dict,
) -> None:
    """Leave the maintainer's own entry alone; otherwise append tapedeck's.

    `subject` is tapedeck's own — never derived from `product` — so a chatty
    maintainer can never swallow a paragraph into the one-line heading a
    chronology entry is supposed to be. `product` becomes the body beneath it,
    kept whole: the maintainer's account of the run belongs to the record, just
    not to the index line that has to stay greppable.

    `before_log` is the chronology as it stood before this run began. If the file
    no longer starts with those bytes, the append-only violation the gate already
    catches has happened and there is nothing safe to reconcile onto — the gate is
    left to report it as it always has.
    """
    log = wiki / layout.LOG
    if not log.is_file():
        return
    now = log.read_bytes()
    if not now.startswith(before_log):
        return
    fresh = now[len(before_log) :].decode("utf-8", errors="replace")
    if layout.entries(fresh):
        return  # the agent already left a well-formed entry of its own

    heading = f"## [{layout.today()}] {op} | {subject}"
    body = []
    told = product.strip()
    if told:
        body.append(told)
    sentence = cost_sentence(cost)
    if sentence:
        body.append(sentence)
    entry = heading + ("\n\n" + "\n\n".join(body) if body else "") + "\n"

    current = now.decode("utf-8", errors="replace")
    log.write_text(current + "\n" + entry, encoding="utf-8")
