"""Model first pass over unlabelled rulings, written to a quarantine file.

The plan permits model assistance for a first pass **only** if every example is
human-reviewed and the assistance is disclosed. This module does the first half;
`cli.py --review-first-pass` does the second; and `schema.validate_example`
enforces it, refusing any row still marked `model-first-pass` in the golden set.

Nothing here writes to `data/golden.jsonl`. Ever.

What the first pass can and cannot ground
-----------------------------------------

**HSN heading — well grounded.** The authority determined it in the same
document, and `ruling_outcome` reads it out. HSN is the Customs Tariff, which
GST 2.0 did not touch, so a 2018 ruling's heading is still correct today.

**Slab — looked up, never recalled.** The Gazette notifications are archived
and hash-pinned in `data/reference/primary/`, so the slab is read out of the
document via `schedule_lookup`. That is a lookup, not a judgement, and it is
the one place model assistance carries almost no risk — the failure mode this
benchmark measures is a model reciting the pre-2025 table from memory, and
nothing here is recalled.

A slab is proposed **only when the heading resolves to exactly one entry**.
Headings that appear in several schedules — 7418 on whether an article is a
household article of copper, 8711 on engine capacity, 2202 on added sugar,
9608 on pens versus pencils — are left `UNCERTAIN` with every competing entry
recorded, because choosing between them is a judgement about the goods.

    python -m harness.label.first_pass --stale 12
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness.collect.aar import cached_pdf_for, extract_pdf_text
from harness.collect.ruling_outcome import extract_outcome
from harness.collect.schedule_lookup import lookup
from harness.schema import (
    UNCERTAIN,
    Example,
    append_jsonl,
    next_id,
    read_jsonl,
    validate_example,
)

GOLDEN = Path("data/golden.jsonl")
QUARANTINE = Path("data/first_pass.jsonl")

#: The one thing the first pass is allowed to conclude on its own: if the rate
#: the authority *held* was 12%, that slab no longer exists, so the rate moved.
#: Where it moved TO still needs Notification 9/2025 and is never proposed.
#:
#: Deliberately narrow. The earlier version keyed on any 12% anywhere in the
#: document and was wrong on 8 of 29 rulings, because an applicant arguing for
#: 12% and losing does not make 12% the rate.


def suggest(record: dict, ex_id: str) -> Example:
    """One quarantined suggestion. Never returns a slab it cannot defend."""
    meta = record.get("collection_meta", {})
    outcome = None
    pdf = cached_pdf_for(record)
    if pdf.exists():
        try:
            text, _ = extract_pdf_text(pdf.read_bytes())
            outcome = extract_outcome(text)
        except Exception:  # noqa: BLE001 - a suggestion is never worth a crash
            outcome = None

    hsn4 = None
    hsn_basis = "no operative ruling located"
    if outcome and outcome.headings:
        hsn4 = outcome.headings[0][:4]
        hsn_basis = (
            f"authority's operative ruling: {outcome.headings} "
            f"({outcome.confidence})"
        )

    # The rate moved only if the rate the authority *held* was the abolished
    # one. Scanning the whole document cannot tell a holding from a rejected
    # contention: in the pen-tips ruling the applicant argued 12% and the
    # authority placed the goods in Schedule III, which was 18%. Tagging on any
    # mention of 12% was wrong on 8 of 29 rulings.
    held = outcome.held_rate if outcome else None
    rate_moved = held == "12"
    if held is None:
        moved_basis = (
            "unknown — the operative ruling names no schedule or rate, so the "
            "pre-2025 rate could not be established. Read the order."
        )
    elif rate_moved:
        moved_basis = (
            f"the authority held {held}%"
            + (f" (Schedule {outcome.schedule} of Notification 1/2017)" if outcome and outcome.schedule else "")
            + ", a slab abolished on 22 Sep 2025"
        )
    else:
        moved_basis = (
            f"the authority held {held}%"
            + (f" (Schedule {outcome.schedule})" if outcome and outcome.schedule else "")
            + ", not 12%. Any 12% in this ruling is the applicant's argument, "
            "not the holding. Whether the rate moved still needs Notification 9/2025."
        )

    # Slab, looked up in the archived Gazette — a document read, not a rate
    # recalled. Proposed only when the heading resolves to exactly one entry;
    # a heading that appears in more than one schedule is left UNCERTAIN with
    # the competing entries recorded, because choosing between them is a
    # judgement about the goods.
    slab = UNCERTAIN
    slab_conf = "none"
    slab_basis = "no heading established, so nothing to look up"
    alternatives: list[str] = []

    if hsn4:
        found = lookup(hsn4)
        if found is None:
            slab_basis = "archived notifications not present; run make verify-sources"
        elif found.slab:
            slab = found.slab
            slab_conf = "grounded in the archived Gazette"
            where = (
                f"Notification 9/2025 Schedule {found.schedule}"
                if found.schedule
                else "Notification 10/2025 (exempt)"
            )
            entry = (found.entries or [None])[0]
            slab_basis = f"{hsn4} appears once, in {where}: " + (
                entry.text[:180] if entry else found.exempt_entries[0][:180]
            )
        elif found.ambiguous:
            alternatives = [f"Sch {e.schedule} = {e.slab}%: {e.text[:150]}" for e in found.entries]
            alternatives += [f"EXEMPT (0%): {x[:150]}" for x in found.exempt_entries]
            slab_basis = (
                f"{hsn4} appears in {len(alternatives)} places in the notifications. "
                "Choosing between them is a judgement about these goods, not a lookup."
            )
        else:
            slab_basis = f"{hsn4} has no current rated or exempt entry"

    notes = {
        "slab_confidence": slab_conf,
        "slab_basis": slab_basis,
        "slab_alternatives": alternatives,
        "hsn_confidence": "high" if hsn4 else "none",
        "hsn_basis": hsn_basis,
        "rate_moved": rate_moved,
        "rate_moved_basis": moved_basis,
        "authority_held_rate": held,
        "authority_schedule": outcome.schedule if outcome else None,
        "conditional": bool(outcome and outcome.is_conditional),
        "quote": outcome.quote[:400] if outcome else "",
        "model": "claude-opus-5",
    }

    if slab != UNCERTAIN:
        justification = (
            f"Heading {hsn4} per the authority's operative ruling; "
            f"{slab}% per {slab_basis.split(':')[0]}."
        )
    elif hsn4:
        justification = (
            f"Heading {hsn4} per the authority's operative ruling. Slab not "
            f"proposed: {slab_basis}"
        )
    else:
        justification = "No operative ruling located; nothing grounded to suggest."

    return Example(
        id=ex_id,
        input=record["input"],
        slab=slab,
        hsn4=hsn4,
        answerable=True,
        justification=justification,
        difficulty="hard",
        tags=["rate-changed-2025"] if rate_moved else [],
        source=record.get("source", ""),
        source_id=record.get("source_id", ""),
        collected_at=record.get("collected_at", ""),
        labelled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        labeller_notes="model first pass; requires human review before use",
        labelled_by="model-first-pass",
        collection_meta=meta,
        model_notes=notes,
    )


def main() -> int:
    from harness.label.cli import load_pool, select_queue

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stale", metavar="RATE", default=None)
    ap.add_argument("--source", default="aar")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=QUARANTINE)
    args = ap.parse_args()

    if args.out.resolve() == GOLDEN.resolve():
        print("refusing to write a model first pass into the golden set", file=sys.stderr)
        return 2

    labelled = list(read_jsonl(GOLDEN))
    existing = list(read_jsonl(args.out))
    done = {e.source_id for e in [*labelled, *existing] if e.source_id}

    queue = select_queue(load_pool(), done, source=args.source, stale=args.stale)
    if args.limit:
        queue = queue[: args.limit]
    if not queue:
        print("nothing to suggest with those settings")
        return 0

    suggestions: list[Example] = []
    all_ids = [*labelled, *existing]
    headings = slabs = ambiguous = 0
    for record in queue:
        ex = suggest(record, next_id([*all_ids, *suggestions]))
        problems = validate_example(ex, quarantine=True)
        if problems:
            print(f"  skipping {ex.source_id}: {problems}", file=sys.stderr)
            continue
        suggestions.append(ex)
        headings += bool(ex.hsn4)
        slabs += ex.slab != UNCERTAIN
        ambiguous += bool(ex.model_notes.get("slab_alternatives"))

    append_jsonl(args.out, suggestions)

    n = len(suggestions)
    print(f"\n  wrote {n} suggestion(s) to {args.out}")
    print(f"  heading from the authority's ruling : {headings}/{n}")
    print(f"  slab read from the archived Gazette : {slabs}/{n}")
    print(f"  heading spans several schedules     : {ambiguous}/{n} — left for you")
    print(
        "\n  These are NOT dataset examples. Review them with:\n"
        "      python -m harness.label.cli --review-first-pass\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
