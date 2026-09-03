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

**Slab — poorly grounded, and the module says so.** Deriving it needs the entry
in Notification 9/2025, and `data/reference/rate_schedule.md` is explicitly not
yet verified line-by-line against the Gazette. So a slab is proposed only where
a documented rule reaches it, and is otherwise left as `UNCERTAIN` rather than
guessed. A guess here is worse than a blank: it would anchor the reviewer on
exactly the examples where model priors are most likely to be the pre-2025
table, which is the error this whole slice exists to measure.

    python -m harness.label.first_pass --stale 12
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness.collect.aar import cached_pdf_for, extract_pdf_text
from harness.collect.ruling_outcome import extract_outcome
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

    # The slab is not proposed. See the module docstring: the reference needed
    # to derive it is unverified, and a guess would anchor the reviewer on
    # precisely the examples where model priors are least trustworthy.
    notes = {
        "slab_confidence": "none",
        "slab_basis": (
            "not derived — Notification 9/2025 entry required, and "
            "data/reference/rate_schedule.md is not yet verified line-by-line"
        ),
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

    return Example(
        id=ex_id,
        input=record["input"],
        slab=UNCERTAIN,
        hsn4=hsn4,
        answerable=True,
        justification=(
            f"Heading {hsn4} per the authority's operative ruling. "
            "Slab not derived; requires Notification 9/2025."
            if hsn4
            else "No operative ruling located; nothing grounded to suggest."
        ),
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
    grounded = 0
    for record in queue:
        ex = suggest(record, next_id([*all_ids, *suggestions]))
        problems = validate_example(ex, quarantine=True)
        if problems:
            print(f"  skipping {ex.source_id}: {problems}", file=sys.stderr)
            continue
        suggestions.append(ex)
        if ex.hsn4:
            grounded += 1

    append_jsonl(args.out, suggestions)

    print(f"\n  wrote {len(suggestions)} suggestion(s) to {args.out}")
    print(f"  heading grounded in the authority's ruling: {grounded}/{len(suggestions)}")
    print(f"  slab proposed: 0/{len(suggestions)} — see the module docstring for why")
    print(
        "\n  These are NOT dataset examples. Review them with:\n"
        "      python -m harness.label.cli --review-first-pass\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
