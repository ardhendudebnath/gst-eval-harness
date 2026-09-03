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
    #: Which reasoning switch this family uses. The three are incompatible and
    #: sending the wrong one is silently ignored, so it is recorded per model
    #: rather than guessed per provider. See providers/openai_compat.py.
    reasoning_style: str = ""
    #: Published container image, where one exists. This is the evidence for
    #: the plan's "one open-weight model you could self-host" — a model with a
    #: pullable image and a documented run command is demonstrably
    #: self-hostable, which an inference from parameter count is not.
    nim_image: str = ""

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
        model_id="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        reasoning_style="system_toggle",
        nim_image="nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5:latest",
        note="has a published NIM container, so self-hostability is "
             "demonstrable; record NVIDIA's price before publishing cost",
    ),
    # The same model on your own GPU. Identical wire format, so the only
    # difference is NIM_BASE_URL — which is the whole point: the open-weight
    # row can be reproduced locally, and that is the bridge to project 03.
    "open-weight-local": ModelSpec(
        key="open-weight-local",
        provider="nim",
        model_id="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        reasoning_style="system_toggle",
        nim_image="nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5:latest",
        note="self-hosted; cost is your GPU time, not a per-token price",
    ),
    # Lighter open-weight option: 30B total with 3B active runs on far less
    # VRAM than a 49B dense model, at the price of a different reasoning
    # switch and no published container to point at.
    "open-weight-lite": ModelSpec(
        key="open-weight-lite",
        provider="nvidia",
        model_id="nvidia/nemotron-3.5-lightning-30b-a3b",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        reasoning_style="chat_template",
        note="30B/3B-active — lighter to self-host; price unrecorded",
    ),
    # Optional extra: open weights at frontier scale. Not the open-weight
    # entry, because the plan asks for one you could self-host.
    "open-weight-xl": ModelSpec(
        key="open-weight-xl",
        provider="nvidia",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        tier="open-weight",
        usd_in_per_m=0.0,
        usd_out_per_m=0.0,
        reasoning_style="chat_template",
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
