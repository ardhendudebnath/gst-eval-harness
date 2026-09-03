"""Cost, and the metric almost nobody publishes.

    cost_per_correct_answer = total_cost / number_of_correct_answers

Different from accuracy and different from cost, and it reorders leaderboards:
a model at 84% for ₹0.30 per correct answer beats one at 89% for ₹2.10 in most
real deployments.

Two rules the plan is firm about and this module enforces:

  * **Prices carry a date.** Every figure is stamped with when the prices were
    read. A cost table without one is not reproducible four months later.
  * **No price, no number.** A model whose price has not been read produces
    `None`, not a zero — a fabricated cost is worse than a blank cell, because
    it silently reorders the ranking this metric exists to produce.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.runners.registry import (
    FX_READ_ON,
    PRICES_READ_ON,
    USD_TO_INR,
    ModelSpec,
    priced,
)


@dataclass(slots=True)
class CostReport:
    model_key: str
    model_id: str
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    calls: int
    correct: int
    usd_total: float | None
    usd_per_correct: float | None
    inr_per_correct: float | None
    p50_latency_ms: int
    p95_latency_ms: int
    prices_read_on: str = PRICES_READ_ON
    fx_read_on: str = FX_READ_ON
    #: Why a cost is missing, when it is.
    unpriced_reason: str | None = None

    def as_row(self) -> dict:
        return {
            "model": self.model_key,
            "model_id": self.model_id,
            "calls": self.calls,
            "correct": self.correct,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "usd_total": None if self.usd_total is None else round(self.usd_total, 4),
            "usd_per_correct": (
                None if self.usd_per_correct is None else round(self.usd_per_correct, 6)
            ),
            "inr_per_correct": (
                None if self.inr_per_correct is None else round(self.inr_per_correct, 4)
            ),
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "prices_read_on": self.prices_read_on,
            "unpriced_reason": self.unpriced_reason,
        }


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    # Nearest-rank: with 20 samples p95 is the 19th, not an interpolation
    # between two latencies that were never actually observed.
    rank = max(1, min(len(ordered), round(pct / 100 * len(ordered))))
    return ordered[rank - 1]


def build(
    spec: ModelSpec,
    completions: list,
    correct: int,
) -> CostReport:
    """Aggregate a run's completions into a cost report.

    `completions` are `harness.runners.base.Completion` objects; failed calls
    are counted and still contribute whatever tokens they burned.
    """
    tokens_in = sum(c.tokens_in for c in completions)
    tokens_out = sum(c.tokens_out for c in completions)
    cached = sum(c.cached_tokens_in for c in completions)
    latencies = [c.latency_ms for c in completions if c.latency_ms]

    usd = usd_per = inr_per = None
    reason = None
    if not priced(spec):
        reason = spec.note or f"no price recorded for {spec.key!r}"
    else:
        usd = spec.cost_usd(tokens_in, tokens_out)
        if correct > 0:
            usd_per = usd / correct
            inr_per = usd_per * USD_TO_INR
        else:
            reason = "no correct answers, so cost per correct answer is undefined"

    return CostReport(
        model_key=spec.key,
        model_id=spec.model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens_in=cached,
        calls=len(completions),
        correct=correct,
        usd_total=usd,
        usd_per_correct=usd_per,
        inr_per_correct=inr_per,
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        unpriced_reason=reason,
    )
