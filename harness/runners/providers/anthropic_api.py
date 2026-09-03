"""Anthropic adapter.

Deliberately named `anthropic_api` rather than `anthropic`: a module called
`anthropic.py` inside this package shadows the SDK of the same name and breaks
the import from inside the package itself.
"""

from __future__ import annotations

import os

from harness.runners.base import Completion, RunnerError, timed
from harness.runners.registry import ModelSpec

#: Room for the answer plus the thinking that current models do by default —
#: thinking tokens count toward the output cap, so a classification-sized
#: budget truncates the answer mid-sentence and scores as a wrong prediction.
MAX_TOKENS = 4000


class AnthropicRunner:
    provider = "anthropic"

    def __init__(self, spec: ModelSpec, *, effort: str | None = None, timeout: float = 120.0):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RunnerError(
                'the anthropic SDK is not installed; pip install -e ".[models]"'
            ) from exc

        self._sdk = anthropic
        self.spec = spec
        self.model = spec.model_id
        self.effort = effort
        # A zero-arg client resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or an `ant auth login` profile — an unset env var does not mean
        # there are no credentials.
        self._client = anthropic.Anthropic(timeout=timeout)

    @timed
    def run(self, prompt: str, *, system: str | None = None) -> Completion:
        kwargs = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}

        blank = Completion(
            text="", model=self.model, provider=self.provider,
            tokens_in=0, tokens_out=0, latency_ms=0,
        )
        try:
            resp = self._client.messages.create(**kwargs)
        except self._sdk.RateLimitError as exc:
            blank.error = f"rate_limit: {exc}"
            return blank
        except self._sdk.APIStatusError as exc:
            blank.error = f"http_{exc.status_code}: {exc}"
            return blank
        except self._sdk.APIConnectionError as exc:
            blank.error = f"connection: {exc}"
            return blank

        text = "".join(b.text for b in resp.content if b.type == "text")

        # A safety decline is an unanswered example, not a wrong answer, and
        # the two mean different things on a leaderboard.
        error = None
        if resp.stop_reason == "refusal":
            detail = getattr(resp, "stop_details", None)
            error = f"refusal: {getattr(detail, 'category', 'unknown')}"

        usage = resp.usage
        return Completion(
            text=text,
            model=resp.model,
            provider=self.provider,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cached_tokens_in=getattr(usage, "cache_read_input_tokens", 0) or 0,
            latency_ms=0,  # set by @timed
            request_id=getattr(resp, "_request_id", None),
            stop_reason=resp.stop_reason,
            error=error,
            extra={"effort": self.effort} if self.effort else {},
        )


def available() -> bool:
    """True when a call could plausibly be made without prompting for a key."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    from pathlib import Path

    return (Path.home() / ".config" / "anthropic").exists()
