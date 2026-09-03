"""The interface every model runner implements.

One method, one return shape. A runner knows how to send a prompt to one
provider and report what it cost; it knows nothing about GST, prompts, or
scoring. That separation is what lets the same scorer grade every provider.

Every field in `Completion` is needed downstream: the text to score, the token
counts and latency to compute cost-per-correct-answer, and the resolved model
id so a result file can never be mistaken for a different model's run.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class Completion:
    """One model call, with everything the leaderboard needs to grade and price it."""

    text: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    #: Provider-side cache accounting, where the provider reports it. Cached
    #: input is billed differently, so cost is wrong without it.
    cached_tokens_in: int = 0
    #: Provider request id, for reporting a bad response back to the provider.
    request_id: str | None = None
    stop_reason: str | None = None
    #: Set when the call failed. `text` is empty and the row is scored as wrong
    #: rather than silently dropped — a model that errors on an example has not
    #: answered it, and quietly excluding those inflates accuracy.
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class Runner(Protocol):
    """A provider adapter. Implementations live in `providers/`."""

    provider: str
    model: str

    def run(self, prompt: str, *, system: str | None = None) -> Completion:
        ...


class RunnerError(RuntimeError):
    """Raised for configuration problems — a missing key, an unknown model."""


def timed(fn):
    """Wrap a provider call so latency is measured the same way everywhere.

    Measured around the whole call including retries the SDK performs
    internally, because that is the latency a user of the system would see.
    """

    def wrapper(*args, **kwargs) -> Completion:
        started = time.perf_counter()
        completion = fn(*args, **kwargs)
        completion.latency_ms = int((time.perf_counter() - started) * 1000)
        return completion

    return wrapper
