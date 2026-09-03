"""Re-apply the current collection filters to an already-collected raw pool.

Scope rules change as the guideline tightens. Re-collecting from scratch to pick
up a new rule is slow and hostile to a rate-limited upstream, so this replays the
current filters over what is already on disk.

    python -m harness.collect.rescreen data/raw/off.jsonl --dry-run
    python -m harness.collect.rescreen data/raw/off.jsonl

Refuses to touch a pool whose records are already labelled — a raw record backing
a golden row must not vanish underneath it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from harness.collect.normalise import in_length_bounds
from harness.schema import out_of_scope_term, read_jsonl

GOLDEN = Path("data/golden.jsonl")


def _dedupe_key(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _haystack(rec: dict) -> str:
    """Everything a scope rule should be able to see.

    Includes the catalogue category and the ruling brief, because the excerpt
    itself often never names the family: a listing reading "Thums up, 250 ml"
    says nothing about carbonation, and a ruling excerpt about a manufacturing
    process may only be identifiable as tobacco from its brief.
    """
    meta = rec.get("collection_meta", {})
    return " ".join(
        [
            rec.get("input", ""),
            str(meta.get("categories") or ""),
            str(meta.get("labels") or ""),
            str(meta.get("ruling_brief") or ""),
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pool", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.pool.exists():
        print(f"no such pool: {args.pool}", file=sys.stderr)
        return 1

    records = [
        json.loads(line)
        for line in args.pool.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    labelled_source_ids = {e.source_id for e in read_jsonl(GOLDEN) if e.source_id}

    kept: list[dict] = []
    seen: set[str] = set()
    dropped: Counter[str] = Counter()
    families: Counter[str] = Counter()
    protected = 0

    for rec in records:
        # Never drop a record that already backs a labelled example.
        if rec.get("source_id") in labelled_source_ids:
            kept.append(rec)
            seen.add(_dedupe_key(rec["input"]))
            protected += 1
            continue

        if term := out_of_scope_term(_haystack(rec)):
            dropped["out_of_scope"] += 1
            families[term] += 1
            continue
        if not in_length_bounds(rec["input"]):
            dropped["length"] += 1
            continue
        key = _dedupe_key(rec["input"])
        if key in seen:
            dropped["duplicate"] += 1
            continue

        seen.add(key)
        kept.append(rec)

    print(f"  pool:     {len(records)} records")
    print(f"  kept:     {len(kept)}" + (f"  ({protected} protected as already labelled)" if protected else ""))
    print(f"  dropped:  {sum(dropped.values())}  {dict(dropped)}")
    if families:
        print(f"  families: {dict(families.most_common())}")

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    if not dropped:
        print("\n  nothing to do")
        return 0

    backup = args.pool.with_suffix(args.pool.suffix + ".bak")
    shutil.copy2(args.pool, backup)
    with args.pool.open("w", encoding="utf-8") as fh:
        for rec in kept:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n  rewrote {args.pool}  (previous copy at {backup.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
