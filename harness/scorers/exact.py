"""Deterministic scoring. No model is involved in any of this.

The project plan's scoring hierarchy is cheapest-method-first, and three of the
four fields never need more than exact match:

  slab        closed label set                 -> exact match
  hsn4        4-digit heading                  -> exact match, chapter partial
  answerable  boolean                          -> precision / recall on refusal
  justification  open-ended                    -> LLM judge (week 5, not here)

The stale-slab rate is scored separately rather than folded into accuracy,
because "wrong" and "quoting a rate that was abolished" are different failures.
A model answering 12% or 28% is not merely inaccurate — it is reciting a
superseded schedule, and that is the finding this benchmark was built to
measure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from harness.prompt import Parsed
from harness.schema import ABOLISHED_SLABS, SLAB_ABOLISHED_ON, UNANSWERABLE, Example

# --------------------------------------------------------------------------
# Abolished rates cited in the reasoning, not just given as the answer
# --------------------------------------------------------------------------
#
# Scoring only the answer field understates the failure. In the first real run,
# three of four refusals reached UNANSWERABLE *by way of* a dead rate --
#
#     "The goods comprise slide fasteners (12% GST) and parts/sliders (18%
#      GST), so no unique rate can be assigned."
#
# -- which scored as an abstention. The model is reciting a superseded schedule
# and then declining on the strength of it; that is the same failure wearing a
# different hat, and it was invisible.

_RATE_MENTION = re.compile(
    r"(?<![\d.])(" + "|".join(sorted(ABOLISHED_SLABS, key=len, reverse=True)) + r")"
    r"\s*(?:%|per\s*ce?nt\b|percent\b)",
    re.I,
)

#: Language that shows the model knows the rate is historical. "The rate was
#: 12% until September 2025" is correct GST history, not staleness, and
#: counting it would manufacture the finding this metric exists to detect.
_HISTORICAL = re.compile(
    r"\b(?:was|were|used\s+to|previously|formerly|earlier|erstwhile|hitherto"
    r"|prior\s+to|before|until|till|up\s*to|upto|then[-\s]existing"
    r"|abolish\w*|omitt?\w*|remov\w*|withdraw\w*|superseded?|replac\w*"
    r"|no\s+longer|ceased?|discontinu\w*|revised?|changed?|pre[-\s]?2025"
    r"|since|w\.e\.f\.?|with\s+effect\s+from)\b",
    re.I,
)

#: How far either side of the mention to look for that language.
_WINDOW_BEFORE, _WINDOW_AFTER = 120, 90


def find_abolished_citations(text: str) -> list[str]:
    """Abolished rates asserted as current anywhere in `text`.

    A mention wrapped in historical language is not counted. This is a
    heuristic over free prose and it will not be perfect either way; it is
    reported as its own metric rather than folded into the headline so the
    judgement it makes stays visible and arguable.
    """
    if not text:
        return []
    found: list[str] = []
    for m in _RATE_MENTION.finditer(text):
        window = text[max(0, m.start() - _WINDOW_BEFORE): m.end() + _WINDOW_AFTER]
        if _HISTORICAL.search(window):
            continue
        rate = m.group(1)
        if rate not in found:
            found.append(rate)
    return found


@dataclass(slots=True)
class RowScore:
    """How one prediction did against one gold example."""

    id: str
    slab_correct: bool
    hsn_correct: bool
    chapter_correct: bool
    abstention_correct: bool
    #: The abolished rate the model quoted, if it quoted one.
    stale_slab: str | None = None
    #: Abolished rates asserted as current anywhere in the response, including
    #: inside a refusal. Superset of `stale_slab` when the answer is one too.
    stale_cited: tuple[str, ...] = ()
    unparseable: bool = False
    errored: bool = False
    predicted_slab: str | None = None
    gold_slab: str = ""

    @property
    def any_credit(self) -> bool:
        return self.slab_correct

    @property
    def recites_dead_schedule(self) -> bool:
        """Answered with an abolished rate, or reasoned from one."""
        return bool(self.stale_slab or self.stale_cited)


def score_row(gold: Example, pred: Parsed, *, errored: bool = False,
              text: str = "") -> RowScore:
    """Grade one prediction. A failed call scores as wrong, never as skipped.

    Dropping errored rows would inflate accuracy for whichever model errors
    most, which is exactly backwards.

    `text` is the model's full response. It is scanned for abolished rates
    asserted as current, which the answer field alone cannot show.
    """
    cited = tuple(find_abolished_citations(text))

    if errored or pred.unparseable:
        return RowScore(
            id=gold.id,
            slab_correct=False,
            hsn_correct=False,
            chapter_correct=False,
            abstention_correct=False,
            # An unparseable answer can still have recited a dead rate on the
            # way to being unparseable.
            stale_cited=cited,
            unparseable=pred.unparseable,
            errored=errored,
            gold_slab=gold.slab,
        )

    slab_correct = pred.slab == gold.slab
    stale = pred.slab if pred.slab in ABOLISHED_SLABS else None

    hsn_correct = bool(gold.hsn4 and pred.hsn4 and pred.hsn4 == gold.hsn4)
    chapter_correct = bool(
        gold.hsn4 and pred.hsn4 and pred.hsn4[:2] == gold.hsn4[:2]
    )

    # Abstention: did the model decline exactly when it should have?
    gold_answerable = gold.slab != UNANSWERABLE
    pred_answerable = pred.slab != UNANSWERABLE if pred.slab else None
    abstention_correct = pred_answerable == gold_answerable

    return RowScore(
        id=gold.id,
        slab_correct=slab_correct,
        hsn_correct=hsn_correct,
        chapter_correct=chapter_correct,
        abstention_correct=abstention_correct,
        stale_slab=stale,
        stale_cited=cited,
        predicted_slab=pred.slab,
        gold_slab=gold.slab,
    )


@dataclass(slots=True)
class Summary:
    """Aggregate scores for one model over one run."""

    n: int = 0
    slab_acc: float = 0.0
    hsn_acc: float = 0.0
    chapter_acc: float = 0.0
    abstention_acc: float = 0.0
    stale_slab_rate: float = 0.0
    stale_by_slab: dict[str, int] = field(default_factory=dict)
    #: Responses reciting an abolished rate as current anywhere, answer or
    #: reasoning. Always >= stale_slab_rate; the gap is the refusals that got
    #: there through a dead schedule.
    stale_cited_rate: float = 0.0
    stale_cited_by_slab: dict[str, int] = field(default_factory=dict)
    unparseable: int = 0
    errored: int = 0
    #: Abstention treated as a detection problem: did it decline when it should?
    abstain_precision: float = 0.0
    abstain_recall: float = 0.0
    abstain_f1: float = 0.0
    n_hsn_gradable: int = 0

    def as_row(self) -> dict:
        return {
            "n": self.n,
            "slab_acc": round(self.slab_acc, 4),
            "hsn_acc": round(self.hsn_acc, 4),
            "chapter_acc": round(self.chapter_acc, 4),
            "abstention_acc": round(self.abstention_acc, 4),
            "abstain_f1": round(self.abstain_f1, 4),
            "stale_slab_rate": round(self.stale_slab_rate, 4),
            "stale_by_slab": self.stale_by_slab,
            "stale_cited_rate": round(self.stale_cited_rate, 4),
            "stale_cited_by_slab": self.stale_cited_by_slab,
            "unparseable": self.unparseable,
            "errored": self.errored,
        }


def summarise(rows: list[RowScore]) -> Summary:
    if not rows:
        return Summary()

    n = len(rows)
    s = Summary(n=n)
    s.slab_acc = sum(r.slab_correct for r in rows) / n
    s.abstention_acc = sum(r.abstention_correct for r in rows) / n
    s.unparseable = sum(r.unparseable for r in rows)
    s.errored = sum(r.errored for r in rows)

    # HSN is only gradable where the gold row has a heading.
    gradable = [r for r in rows if r.gold_slab != UNANSWERABLE or r.hsn_correct]
    hsn_rows = [r for r in rows if not r.errored and not r.unparseable]
    s.n_hsn_gradable = len(hsn_rows)
    if hsn_rows:
        s.hsn_acc = sum(r.hsn_correct for r in hsn_rows) / len(hsn_rows)
        s.chapter_acc = sum(r.chapter_correct for r in hsn_rows) / len(hsn_rows)

    stale = [r for r in rows if r.stale_slab]
    s.stale_slab_rate = len(stale) / n
    counts: dict[str, int] = {}
    for r in stale:
        counts[r.stale_slab] = counts.get(r.stale_slab, 0) + 1
    s.stale_by_slab = dict(sorted(counts.items()))

    cited = [r for r in rows if r.recites_dead_schedule]
    s.stale_cited_rate = len(cited) / n
    cited_counts: dict[str, int] = {}
    for r in cited:
        for slab in {*(r.stale_cited), *([r.stale_slab] if r.stale_slab else [])}:
            cited_counts[slab] = cited_counts.get(slab, 0) + 1
    s.stale_cited_by_slab = dict(sorted(cited_counts.items()))

    # Abstention as detection: positive class = "should decline".
    tp = sum(
        1 for r in rows
        if r.gold_slab == UNANSWERABLE and r.predicted_slab == UNANSWERABLE
    )
    fp = sum(
        1 for r in rows
        if r.gold_slab != UNANSWERABLE and r.predicted_slab == UNANSWERABLE
    )
    fn = sum(
        1 for r in rows
        if r.gold_slab == UNANSWERABLE and r.predicted_slab != UNANSWERABLE
    )
    s.abstain_precision = tp / (tp + fp) if (tp + fp) else 0.0
    s.abstain_recall = tp / (tp + fn) if (tp + fn) else 0.0
    if s.abstain_precision + s.abstain_recall:
        s.abstain_f1 = (
            2 * s.abstain_precision * s.abstain_recall
            / (s.abstain_precision + s.abstain_recall)
        )
    return s


def describe_stale(summary: Summary) -> str:
    """One line naming which superseded table a model is reciting."""
    if not summary.stale_by_slab:
        return "no abolished slab quoted"
    parts = [
        f"{slab}% (abolished {SLAB_ABOLISHED_ON[slab]}) ×{n}"
        for slab, n in summary.stale_by_slab.items()
    ]
    return f"{summary.stale_slab_rate:.1%} — " + ", ".join(parts)
