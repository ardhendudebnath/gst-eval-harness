"""Judge vs human: Cohen's κ, the confusion matrix, and every disagreement.

This is the section of the README that gets read most carefully, so the report
is built to be checkable rather than flattering:

  * **κ is reported whatever it is.** A low κ that is diagnosed is a better
    result than a high one that is not, and the plan says to publish the
    failure rather than hide it.
  * **Every disagreement is listed in full** — the goods, the gold answer, the
    explanation, and both verdicts — because the categorisation of *why* the
    judge disagreed is the finding, and it cannot be done from counts.
  * **Categories are suggested, never assigned.** Deciding which failure mode a
    disagreement belongs to is a judgement about the reasoning, and a model
    grading its own failure modes is circular.

    python -m harness.calibration.judge_calibration --verdicts <file>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from harness.calibration.kappa import cohens_kappa
from harness.scorers.judge import RUBRIC_VERSION

HUMAN = Path("data/judge_labels.jsonl")
OUT = Path("results/judge_calibration.md")

#: The failure modes the plan names, offered to the annotator as a starting
#: vocabulary. The list is a prompt for thought, not a closed set — a mode
#: found in this domain that is not here is the more interesting result.
SUGGESTED_CATEGORIES = [
    "fluent-but-wrong — rewarded a confident explanation that is not sound",
    "unusual-phrasing — penalised sound reasoning that was worded oddly",
    "missed-subtle-error — could not see a factual error in its own domain",
    "wrong-heading-tolerated — accepted a heading inconsistent with gold",
    "circularity-tolerated — accepted 'it is the rate because it is the rate'",
    "stale-authority-tolerated — accepted a superseded notification as basis",
    "over-strict — demanded detail the guideline does not require",
]


@dataclass(slots=True)
class Pair:
    example_id: str
    human: str
    judge: str
    description: str = ""
    gold_slab: str = ""
    gold_hsn: str | None = None
    justification: str = ""
    judge_reason: str = ""

    @property
    def agree(self) -> bool:
        return self.human == self.judge


def load_pairs(verdicts_path: Path, human_path: Path = HUMAN) -> list[Pair]:
    """Join judge verdicts to human labels on example id."""
    human: dict[str, dict] = {}
    if human_path.exists():
        for line in human_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                human[row["example_id"]] = row

    pairs = []
    for line in verdicts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        v = json.loads(line)
        h = human.get(v["example_id"])
        if not h:
            continue  # not yet labelled by a human; not a disagreement
        pairs.append(
            Pair(
                example_id=v["example_id"],
                human=h["verdict"].upper(),
                judge=v["verdict"].upper(),
                description=v.get("description", ""),
                gold_slab=v.get("gold_slab", ""),
                gold_hsn=v.get("gold_hsn"),
                justification=v.get("justification", ""),
                judge_reason=v.get("reason", ""),
            )
        )
    return pairs


def report(pairs: list[Pair], judge_model: str = "unknown") -> str:
    if not pairs:
        return (
            "# Judge calibration\n\n"
            "No paired verdicts yet. Run the judge over examples that also have "
            "human pass/fail labels in `data/judge_labels.jsonl`.\n"
        )

    agreement = cohens_kappa([p.human for p in pairs], [p.judge for p in pairs])
    disagreements = [p for p in pairs if not p.agree]

    lines: list[str] = []
    w = lines.append
    w("# Judge calibration\n")
    w(f"- Judge model: `{judge_model}`")
    w(f"- Rubric: `{RUBRIC_VERSION}`")
    w(f"- Paired examples: **{agreement.n}**\n")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Raw agreement | {agreement.observed:.1%} |")
    w(f"| Expected by chance | {agreement.expected:.1%} |")
    w(f"| **Cohen's κ** | **{agreement.kappa:.3f}** |")
    w(f"| Reading | {agreement.reading} |\n")

    if agreement.kappa < 0.40:
        w(
            "> **The judge is unusable at this κ.** The rubric needs fixing "
            "before any judged score is published. The disagreements below are "
            "the input to that fix — this is a result, not a blocker to hide.\n"
        )
    elif agreement.kappa < 0.60:
        w(
            "> **Moderate.** Usable only with the caveat stated alongside every "
            "judged figure.\n"
        )

    w("## Confusion matrix\n")
    w("```")
    w(agreement.render_matrix(row_name="human", col_name="judge"))
    w("```\n")

    # Directional error matters: over-crediting and over-penalising are
    # different problems with different fixes.
    lenient = sum(1 for p in disagreements if p.human == "FAIL" and p.judge == "PASS")
    strict = sum(1 for p in disagreements if p.human == "PASS" and p.judge == "FAIL")
    w("## Direction of error\n")
    w(f"- Judge too lenient (human FAIL, judge PASS): **{lenient}**")
    w(f"- Judge too strict (human PASS, judge FAIL): **{strict}**\n")
    if lenient > strict:
        w(
            "The judge credits reasoning the annotator rejected. On this task "
            "that usually means fluent-but-unsound explanations are passing.\n"
        )
    elif strict > lenient:
        w(
            "The judge rejects reasoning the annotator accepted. Check whether "
            "the rubric demands detail the guideline never asked for.\n"
        )

    w(f"## Disagreements ({len(disagreements)})\n")
    if not disagreements:
        w("None. With perfect agreement, check the task is not trivially easy.\n")
    else:
        w("Categorise each one. Suggested vocabulary:\n")
        for c in SUGGESTED_CATEGORIES:
            w(f"- {c}")
        w("")
        for p in disagreements:
            w(f"### `{p.example_id}` — human **{p.human}**, judge **{p.judge}**\n")
            if p.description:
                snippet = p.description[:240] + ("…" if len(p.description) > 240 else "")
                w(f"> {snippet}\n")
            w(f"- gold: {p.gold_slab}%, heading {p.gold_hsn or '—'}")
            w(f"- explanation judged: {p.justification[:300] or '(none)'}")
            w(f"- judge's reason: {p.judge_reason or '(none given)'}")
            w("- **category:** _TODO_")
            w("- **what it implies for the rubric:** _TODO_\n")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verdicts", type=Path, required=True)
    ap.add_argument("--human", type=Path, default=HUMAN)
    ap.add_argument("--judge-model", default="unknown")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if not args.verdicts.exists():
        print(f"no verdicts at {args.verdicts}")
        return 1

    pairs = load_pairs(args.verdicts, args.human)
    text = report(pairs, args.judge_model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwritten to {args.out}")

    if pairs:
        k = cohens_kappa([p.human for p in pairs], [p.judge for p in pairs]).kappa
        # Non-zero on an unusable judge so CI can gate on it later.
        return 0 if k >= 0.40 else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
