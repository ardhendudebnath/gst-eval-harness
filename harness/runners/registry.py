"""Models available to the harness, with prices and the date they were read.

Two rules from the project plan are enforced here rather than trusted to
discipline:

**Pin exact versions.** Model behaviour changes under the same name, so every
result file records the exact id string used and the date it ran. Ids here are
complete as-is and never carry an invented date suffix.

**State prices with a date.** `PRICES_READ_ON` is stamped into every cost
report. A leaderboard quoting cost without saying when the prices were read is
not reproducible.

Nothing in this file asserts that a model has been *called*. `verified` stays
False until a run against that model lands in `results/`, and the leaderboard
renders only verified rows — the plan is explicit that naming a model you have
not actually called is a credibility hole.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Anthropic first-party list prices, USD per million tokens.
PRICES_READ_ON = "2026-06-24"

#: Rupees per US dollar, for the ₹/correct-answer column. Update alongside
#: prices; the report prints both currencies and this date.
USD_TO_INR = 88.0
FX_READ_ON = "2026-09-04"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    key: str
    provider: str
    model_id: str
    tier: str
    usd_in_per_m: float
    usd_out_per_m: float
    #: Flipped to True only by a completed run recorded in results/.
    verified: bool = False
    note: str = ""

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        return (
            tokens_in / 1_000_000 * self.usd_in_per_m
            + tokens_out / 1_000_000 * self.usd_out_per_m
        )


#: Anthropic prices are first-party list rates read on PRICES_READ_ON.
#: Non-Anthropic entries carry no price until one is read from that provider
#: and dated — a guessed price silently corrupts cost-per-correct-answer,
#: which is the metric this benchmark exists to publish.
MODELS: dict[str, ModelSpec] = {
    "opus-5": ModelSpec(
        key="opus-5",
        provider="anthropic",
        model_id="claude-opus-5",
        tier="frontier",
        usd_in_per_m=5.00,
        usd_out_per_m=25.00,
    ),
    "sonnet-5": ModelSpec(
        key="sonnet-5",
        provider="anthropic",
        model_id="claude-sonnet-5",
        tier="mid",
        usd_in_per_m=2.00,
        usd_out_per_m=10.00,
    ),
    "haiku-4-5": ModelSpec(
        key="haiku-4-5",
        provider="anthropic",
        model_id="claude-haiku-4-5",
        tier="small",
        usd_in_per_m=1.00,
        usd_out_per_m=5.00,
    ),
    # The open-weight tier the plan asks for: a model you could actually
    # self-host, which is what makes it the bridge to project 03. Served here
    # through NVIDIA's catalog so no GPU is needed to benchmark it.
    #
    # 30B total with 3B active fits on a single GPU, so "could self-host" is
    # true rather than aspirational. The 550B sibling is a stronger model but
    # cannot discharge this requirement — nobody is self-hosting 550B.
    #
    # Price is zero deliberately: it must be read from the provider and dated
    # before any cost figure is published. See `priced()`.
    "open-weight": ModelSpec(
        key="open-weight",
        provider="nvidia",
        model_id="nvidia/nemotron-3.5-lightning-30b-a3b",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        note="record NVIDIA's price for this model, with the date, before "
             "publishing any cost figure",
    ),
    # Optional extra data point: open weights at frontier scale. Not the
    # open-weight entry, because the plan asks for one you could self-host.
    "open-weight-xl": ModelSpec(
        key="open-weight-xl",
        provider="nvidia",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        note="550B — an extra comparison, not self-hostable; price unrecorded",
    ),
}


def get(key: str) -> ModelSpec:
    if key not in MODELS:
        raise KeyError(f"unknown model key {key!r}; known: {sorted(MODELS)}")
    return MODELS[key]


def priced(spec: ModelSpec) -> bool:
    """False when a cost figure for this model would be fabricated."""
    return spec.usd_in_per_m > 0 and spec.usd_out_per_m > 0
