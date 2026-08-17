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


def _cost_line(cost: dict) -> str | None:
    """What the run cost, in the figures the result event reported — nothing more
    than that, so a maintainer that streamed no cost contributes no line at all
    rather than a row of zeroes standing in for one."""
    parts = []
    if "duration_s" in cost:
        parts.append(f"{cost['duration_s']}s")
    if "input_tokens" in cost or "output_tokens" in cost:
        parts.append(
            f"{cost.get('input_tokens', '?')} in / {cost.get('output_tokens', '?')} out tokens"
        )
    if "cost_usd" in cost:
        parts.append(f"${cost['cost_usd']:.2f}")
    return " · ".join(parts) if parts else None


def reconcile_log(
    wiki: Path,
    before_log: bytes,
    op: str,
    product: str,
    cost: dict,
    fallback_subject: str,
) -> None:
    """Leave the maintainer's own entry alone; otherwise append tapedeck's.

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
    subject = " ".join(product.split()) or fallback_subject
    lines = [f"## [{layout.today()}] {op} | {subject}"]
    cost_line = _cost_line(cost)
    if cost_line:
        lines += ["", cost_line]
    current = now.decode("utf-8", errors="replace")
    log.write_text(current + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
