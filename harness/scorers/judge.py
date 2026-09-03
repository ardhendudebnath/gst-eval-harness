"""LLM-as-judge for the one field that is genuinely open-ended.

Slab, HSN and abstention are exact-match — a judge there would be reaching for
the fashionable tool. Only `justification` needs one, and its job is narrow:
**did the model reach its answer by a route that would generalise?**

That question is not the same as "was the answer right", and the rubric is
built around the difference. `guideline.md` WE-5 is the worked case: a hamper
whose components are all 5% can be answered "5% because gift hampers are 5%",
which is the right number by a route that gets the next hamper wrong. The
rubric fails it, and a test pins that.

**The rubric is v1 and provisional.** It was written before any human
disagreement data existed, which is the wrong order — the plan is explicit that
the rubric should be revised once you have looked at real disagreements. The
calibration report exists to drive that revision, and `RUBRIC_VERSION` is
stamped into every verdict so a κ figure can always be traced to the rubric
that produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RUBRIC_VERSION = "v1-provisional"

SYSTEM = (
    "You audit reasoning about Indian GST classification. You judge whether an "
    "explanation reaches its conclusion by sound reasoning, not whether you "
    "like its wording."
)

RUBRIC = """\
You are checking one explanation of a GST classification.

The correct answer, established by a human annotator against the Gazette:
  heading: {gold_hsn}
  slab:    {gold_slab}%

The goods:
---
{description}
---

The explanation to judge:
---
{justification}
---

Answer PASS only if BOTH hold:
  1. It identifies a heading consistent with {gold_hsn}, or explains why the
     goods fall there.
  2. It gives a basis that actually determines the rate — a schedule, an entry,
     an exemption, or the conditional fact that decides between two entries.

Answer FAIL if any of these hold:
  - It gives no heading and no basis.
  - Its heading is inconsistent with {gold_hsn} and it does not justify the
    difference.
  - It is circular: the rate is asserted because it is the rate, or because
    goods "like this" are taxed that way.
  - It relies on a superseded authority — Notification 1/2017, the 12% slab,
    or the 28% slab — as the reason the rate is what it is.
  - It arrives at the right number by a route that would fail on a similar
    good. A right answer for the wrong reason is a FAIL.

Judge the reasoning, not the phrasing. An explanation that is terse, oddly
worded, or differently structured still PASSES if the reasoning holds.

Answer in exactly this format:

VERDICT: PASS or FAIL
REASON: <one sentence>"""


@dataclass(slots=True)
class Verdict:
    passed: bool | None
    reason: str
    rubric_version: str = RUBRIC_VERSION
    unparseable: bool = False

    @property
    def label(self) -> str:
        """The categorical label κ is computed over."""
        if self.passed is None:
            return "UNPARSEABLE"
        return "PASS" if self.passed else "FAIL"


_VERDICT = re.compile(r"^\s*VERDICT\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
_REASON = re.compile(r"^\s*REASON\s*[:\-]\s*(.+?)\s*$", re.I | re.M | re.S)


def build_prompt(description: str, gold_hsn: str | None, gold_slab: str,
                 justification: str) -> str:
    return RUBRIC.format(
        description=description.strip()[:2000],
        gold_hsn=gold_hsn or "(none established)",
        gold_slab=gold_slab,
        justification=(justification or "(the model gave no explanation)").strip()[:1500],
    )


def parse_verdict(text: str) -> Verdict:
    m = _VERDICT.search(text or "")
    if not m:
        return Verdict(None, "", unparseable=True)

    raw = m.group(1).upper()
    # Check FAIL first: "not a PASS" and "FAIL, not PASS" both contain PASS.
    if "FAIL" in raw:
        passed = False
    elif "PASS" in raw:
        passed = True
    else:
        return Verdict(None, "", unparseable=True)

    reason_m = _REASON.search(text)
    reason = " ".join((reason_m.group(1) if reason_m else "").split())[:400]
    return Verdict(passed, reason)


class Judge:
    """Wraps a runner. The judge model is recorded on every verdict's run."""

    def __init__(self, runner):
        self.runner = runner
        self.model = getattr(runner, "model", "unknown")

    def judge(self, description: str, gold_hsn: str | None, gold_slab: str,
              justification: str) -> tuple[Verdict, object]:
        completion = self.runner.run(
            build_prompt(description, gold_hsn, gold_slab, justification),
            system=SYSTEM,
        )
        if not completion.ok:
            return Verdict(None, f"judge call failed: {completion.error}",
                           unparseable=True), completion
        return parse_verdict(completion.text), completion
