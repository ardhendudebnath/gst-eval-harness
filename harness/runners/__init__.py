"""Build a runner from a model key.

    from harness.runners import build
    runner = build("opus-5")
    completion = runner.run(prompt)
"""

from __future__ import annotations

from harness.runners.base import Completion, Runner, RunnerError, timed
from harness.runners.registry import MODELS, ModelSpec, get, priced

__all__ = [
    "Completion", "Runner", "RunnerError", "timed",
    "MODELS", "ModelSpec", "get", "priced", "build",
]


def build(key: str, **kwargs) -> Runner:
    """Construct the runner for `key`. Raises RunnerError if it cannot run."""
    spec = get(key)
    if spec.provider == "anthropic":
        from harness.runners.providers.anthropic_api import AnthropicRunner

        return AnthropicRunner(spec, **kwargs)
    if spec.provider in ("openai", "openrouter"):
        from harness.runners.providers.openai_compat import OpenAICompatRunner

        return OpenAICompatRunner(spec, **kwargs)
    raise RunnerError(f"no adapter for provider {spec.provider!r}")
