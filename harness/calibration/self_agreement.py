"""Annotator self-agreement: the ceiling on every model score in this benchmark.

Compares the original golden labels against a blind re-label produced by
`python -m harness.label.cli --relabel N`, a week or more later.

    python -m harness.calibration.self_agreement --relabel data/relabel-2026-09-17.jsonl

Guideline §7.3: below roughly 85% raw agreement the guideline is too vague —
fix it and re-label the affected batches rather than pressing on.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from harness.calibration.kappa import cohens_kappa
from harness.schema import Example, read_jsonl

FLOOR = 0.85


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("data/golden.jsonl"))
    ap.add_argument("--relabel", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("results/self_agreement.md"))
    args = ap.parse_args()

    original: dict[str, Example] = {
        e.id: e for e in read_jsonl(args.data) if e.is_active
    }
    redone: list[Example] = list(read_jsonl(args.relabel))
    if not redone:
        print(f"no re-labels in {args.relabel}")
        return 1

    paired = [(original[e.id], e) for e in redone if e.id in original]
    if not paired:
        print("no ids in common between the two files")
        return 1

    first = [a.slab for a, _ in paired]
    second = [b.slab for _, b in paired]
    slab = cohens_kappa(first, second)

    ans = cohens_kappa(
        [str(a.answerable) for a, _ in paired],
        [str(b.answerable) for _, b in paired],
    )
    hsn = cohens_kappa(
        [a.hsn4 or "-" for a, _ in paired],
        [b.hsn4 or "-" for _, b in paired],
    )

    disagreements = [(a, b) for a, b in paired if a.slab != b.slab]

    lines: list[str] = []
    w = lines.append
    w("# Annotator self-agreement\n")
    w(f"- Re-label file: `{args.relabel.name}`")
    w(f"- Paired examples: **{slab.n}**\n")
    w("| Field | Raw agreement | Cohen's kappa | Reading |")
    w("|---|---|---|---|")
    for name, a in (("slab", slab), ("answerable", ans), ("hsn4", hsn)):
        w(f"| `{name}` | {a.observed:.1%} | **{a.kappa:.3f}** | {a.reading} |")
    w("")

    verdict = (
        f"Raw slab agreement is {slab.observed:.1%}, at or above the {FLOOR:.0%} floor. "
        "The guideline is specific enough to proceed."
        if slab.observed >= FLOOR
        else f"Raw slab agreement is {slab.observed:.1%}, **below the {FLOOR:.0%} floor**. "
        "The guideline is too vague. Fix it and re-label the affected batches "
        "before running any model."
    )
    w(f"**Verdict.** {verdict}\n")
    w(
        f"**Ceiling.** No model can be meaningfully credited above "
        f"{slab.observed:.1%} on `slab` for this dataset, because that is how "
        "often the annotator agrees with themselves.\n"
    )

    w("## Confusion matrix — slab\n")
    w("```")
    w(slab.render_matrix(row_name="first", col_name="redo"))
    w("```\n")

    if disagreements:
        w(f"## Self-disagreements ({len(disagreements)})\n")
        w("Each of these is a defect in the guideline until proven otherwise.\n")
        for a, b in disagreements:
            w(f"### `{a.id}`  {a.slab} -> {b.slab}\n")
            text = a.input if len(a.input) <= 240 else a.input[:240] + " …"
            w(f"> {text}\n")
            w(f"- first pass: **{a.slab}**, hsn {a.hsn4} — {a.justification}")
            w(f"- re-label:   **{b.slab}**, hsn {b.hsn4} — {b.justification}")
            w("- guideline section to tighten: _TODO_\n")

    report = "\n".join(lines)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nwritten to {args.out}")
    return 0 if slab.observed >= FLOOR else 2


if __name__ == "__main__":
    raise SystemExit(main())
