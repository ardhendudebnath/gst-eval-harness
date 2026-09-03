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

from harness.collect.aar import is_about_services, is_withdrawn, reextract
from harness.collect.normalise import in_length_bounds, normalise
from harness.schema import out_of_scope_term, read_jsonl

GOLDEN = Path("data/golden.jsonl")


def _dedupe_key(text: str) -> str:
    """Content key, matching the collectors' own near-duplicate rule.

    Capped at 400 characters so two copies of the same ruling that diverge in a
    trailing clause still collide.
    """
    import re

    return re.sub(r"[^a-z0-9]+", "", text.lower())[:400]


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
    ap.add_argument(
        "--reextract",
        type=int,
        metavar="WORDS",
        default=None,
        help="rebuild ruling excerpts from cached PDFs at this word cap "
        "(no network; the cap is a policy choice, not a property of the source)",
    )
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
    redacted = 0
    reextracted = 0

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

        # Rulings only: s.97(2)(a) covers goods *or services*, so the clause
        # filter alone lets services through. Replaying it here cleans pools
        # collected before a service term was added to the vocabulary.
        if rec.get("source") == "aar":
            brief = rec.get("collection_meta", {}).get("ruling_brief", "")
            if is_about_services({"brief": brief}):
                dropped["services"] += 1
                continue
            # Withdrawn applications carry no determination and facts the
            # applicant has disowned.
            if is_withdrawn(rec["input"]):
                dropped["withdrawn"] += 1
                continue
        # Rewriting happens before the length and duplicate checks, so both are
        # applied to the text that will actually be shipped.
        if rec.get("source") == "aar":
            if args.reextract:
                rebuilt = reextract(rec, args.reextract)
                if rebuilt is None:
                    dropped["reextract_failed"] += 1
                    continue
                if rebuilt["input"] != rec["input"]:
                    reextracted += 1
                rec = rebuilt

            # Re-run redaction. Filters alone cannot fix a record collected
            # before a redaction pattern existed — the name is already on disk,
            # and only re-normalising removes it.
            cleaned, applied = normalise(rec["input"], is_ruling=True)
            if cleaned != rec["input"]:
                rec["input"] = cleaned
                meta = rec.setdefault("collection_meta", {})
                meta["transforms"] = sorted(set(meta.get("transforms", [])) | set(applied))
                redacted += 1

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
    if redacted:
        print(f"  redacted: {redacted} record(s) further cleaned by current patterns")
    if reextracted:
        print(f"  re-cut:   {reextracted} excerpt(s) rebuilt at {args.reextract} words")
        words = [len(r["input"].split()) for r in kept if r.get("source") == "aar"]
        if words:
            words.sort()
            long_ctx = sum(1 for n in words if n >= 800)
            print(
                f"            ruling words: median={words[len(words) // 2]} "
                f"max={words[-1]}  |  {long_ctx} at 800+ (long_context candidates)"
            )

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0

    if not dropped and not redacted and not reextracted:
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
