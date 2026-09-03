"""Validate the golden set: per-row schema checks plus dataset-level health.

    python -m harness.validate [--data data/golden.jsonl] [--strict]

Exits non-zero on any row error. `--strict` also fails on composition drift,
which is what CI uses once the dataset is frozen.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from harness.schema import (
    TARGET_STRATA,
    Example,
    read_jsonl,
    validate_example,
)

# Composition may drift this far from guideline.md §8 before --strict fails.
STRATUM_TOLERANCE = 0.05
MIN_RATE_CHANGED = 60
MIN_SIZE = 200


def _bar(frac: float, width: int = 24) -> str:
    filled = round(frac * width)
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("data/golden.jsonl"))
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    if not args.data.exists():
        print(f"no dataset at {args.data} yet — nothing to validate.")
        return 0

    examples: list[Example] = list(read_jsonl(args.data))
    if not examples:
        print(f"{args.data} is empty — nothing to validate.")
        return 0

    errors: list[str] = []

    # --- per-row --------------------------------------------------------
    for ex in examples:
        for problem in validate_example(ex):
            errors.append(f"  {ex.id}: {problem}")

    # --- duplicate ids ---------------------------------------------------
    for ex_id, count in Counter(e.id for e in examples).items():
        if count > 1:
            errors.append(f"  duplicate id {ex_id} appears {count} times")

    # --- deprecation pointers resolve ------------------------------------
    ids = {e.id for e in examples}
    for ex in examples:
        if ex.deprecated_by and ex.deprecated_by not in ids:
            errors.append(
                f"  {ex.id}: deprecated_by points at {ex.deprecated_by!r}, "
                "which is not in the dataset"
            )

    active = [e for e in examples if e.is_active]
    deprecated = len(examples) - len(active)

    # --- report -----------------------------------------------------------
    print(f"\n  {args.data}")
    print(f"  {len(active)} active examples" + (f"  ({deprecated} deprecated)" if deprecated else ""))
    print()

    print("  Stratification (target from guideline.md §8)")
    counts = Counter(e.difficulty for e in active)
    warnings: list[str] = []
    for stratum, target in TARGET_STRATA.items():
        n = counts.get(stratum, 0)
        frac = n / len(active) if active else 0.0
        drift = frac - target
        flag = "  <-- off target" if abs(drift) > STRATUM_TOLERANCE else ""
        print(
            f"    {stratum:<13} {_bar(frac)} {n:>4}  {frac:5.1%}  "
            f"(target {target:.0%}, {drift:+.1%}){flag}"
        )
        if abs(drift) > STRATUM_TOLERANCE:
            warnings.append(f"stratum {stratum!r} is {drift:+.1%} off target")

    print("\n  Slab distribution")
    for slab, n in sorted(
        Counter(e.slab for e in active).items(),
        key=lambda kv: -kv[1],
    ):
        print(f"    {slab:<13} {n:>4}  {n / len(active):5.1%}")

    unanswerable = [e for e in active if not e.answerable]
    if unanswerable:
        print(f"\n  Unanswerable reasons ({len(unanswerable)} rows)")
        for reason, n in Counter(
            e.unanswerable_reason or "?" for e in unanswerable
        ).most_common():
            print(f"    {reason:<26} {n:>4}")

    rate_changed = sum(1 for e in active if "rate-changed-2025" in e.tags)
    print(f"\n  Tagged rate-changed-2025: {rate_changed}  (target >= {MIN_RATE_CHANGED})")
    if rate_changed < MIN_RATE_CHANGED:
        warnings.append(
            f"only {rate_changed} rate-changed-2025 examples; "
            f"need >= {MIN_RATE_CHANGED} for a usable confidence interval "
            "on the stale-knowledge finding"
        )

    if len(active) < MIN_SIZE:
        warnings.append(
            f"{len(active)} active examples; below {MIN_SIZE} the confidence "
            "intervals are too wide to say anything (guideline.md §8)"
        )

    print()
    if errors:
        print(f"  FAIL — {len(errors)} error(s):")
        for e in errors[:40]:
            print(e)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    if warnings:
        print(f"  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"    - {w}")
        if args.strict:
            print("\n  FAIL (--strict)")
            return 1
        print()

    print("  OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
