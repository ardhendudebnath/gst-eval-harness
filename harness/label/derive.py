"""Write the Gazette-grounded suggestions into the golden set as derived rows.

    python -m harness.label.derive            # dry run, prints what it would do
    python -m harness.label.derive --write

**This is not labelling and does not pretend to be.** Rows written here carry
`labelled_by: gazette-derived`, never `human-reviewed`, and every downstream
report has to keep them in their own column.

Why they are admissible at all: nothing in them is recalled.

  heading  taken from the authority's own operative ruling in the source
           document, by `ruling_outcome`, and quoted in the row
  slab     read from `data/reference/primary/` by `schedule_lookup`, which
           refuses to resolve any heading appearing in more than one schedule,
           so only unambiguous entries reach this file at all

A model's recollection of Indian GST rates is the pre-2025 table, which is the
error this benchmark measures. None of it is used here, and that is the whole
argument for these rows existing.

What they cannot do:

  * populate `hard` or `adversarial` — those strata exist for the calls a
    lookup cannot make, and assigning them would be exactly the judgement this
    module is avoiding
  * substitute for the human ceiling — self-agreement needs a human labelling
    twice, and these rows have no human in them to disagree with
  * carry the dataset's provenance claim. The README says which rows are which

Promote one by reviewing it: `python -m harness.label.cli --review-first-pass`
overwrites a derived row with a `human-reviewed` one when the annotator gets
to it.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from harness.schema import (
    UNCERTAIN,
    Example,
    append_jsonl,
    read_jsonl,
    validate_example,
)

GOLDEN = Path("data/golden.jsonl")
FIRST_PASS = Path("data/first_pass.jsonl")

#: Word count above which an excerpt is long-context. The only difficulty
#: distinction a lookup is entitled to make: it is a property of the input's
#: length, not a judgement about the goods.
LONG_CONTEXT_WORDS = 800


def difficulty_for(text: str) -> str:
    return "long_context" if len(text.split()) >= LONG_CONTEXT_WORDS else "typical"


def derived_rows() -> list[Example]:
    """Every grounded suggestion, as a derived golden row."""
    out: list[Example] = []
    for line in FIRST_PASS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["slab"] == UNCERTAIN or not r["hsn4"]:
            continue

        notes = r.get("model_notes") or {}
        basis = str(notes.get("slab_basis") or "")[:300]
        out.append(Example(
            id=r["id"],
            input=r["input"],
            slab=r["slab"],
            hsn4=r["hsn4"],
            answerable=r.get("answerable", True),
            justification=r.get("justification") or "",
            difficulty=difficulty_for(r["input"]),
            tags=[t for t in (r.get("tags") or []) if t != "rate-changed-2025"],
            source=r.get("source", "aar"),
            source_id=r.get("source_id", ""),
            collection_meta=r.get("collection_meta") or {},
            labelled_by="gazette-derived",
            labelled_at=str(date.today()),
            labeller_notes=(
                "slab read from the archived notification, heading from the "
                f"authority's operative ruling; no human confirmed it. {basis}"
            ),
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="actually append to the golden set")
    args = ap.parse_args()

    existing = list(read_jsonl(GOLDEN)) if GOLDEN.exists() else []
    have = {e.id for e in existing}
    human = [e for e in existing if e.labelled_by != "gazette-derived"]

    rows = [e for e in derived_rows() if e.id not in have]
    problems = [(e.id, validate_example(e)) for e in rows]
    bad = [(i, p) for i, p in problems if p]

    print(f"\n  golden.jsonl        : {len(existing)} row(s), "
          f"{len(human)} of them human")
    print(f"  derived rows to add : {len(rows)}")
    for eid, probs in bad:
        print(f"    INVALID {eid}: {probs}")
    if bad:
        print("\n  refusing to write invalid rows\n")
        return 1

    from collections import Counter
    print(f"  slabs               : {dict(Counter(e.slab for e in rows))}")
    print(f"  difficulty          : {dict(Counter(e.difficulty for e in rows))}")
    print("\n  These are NOT human labels. They cannot fill the hard or")
    print("  adversarial strata, and they cannot serve as the human ceiling.")

    if not args.write:
        print("\n  dry run — pass --write to append\n")
        return 0

    append_jsonl(GOLDEN, rows)
    print(f"\n  appended {len(rows)} derived row(s) to {GOLDEN}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
