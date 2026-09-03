"""Adapter for OpenAI-compatible chat-completions endpoints.

One class covers both OpenAI itself and OpenRouter, because OpenRouter serves
the same wire format. OpenRouter is how the open-weight tier the project plan
asks for is reached without self-hosting — and it is the bridge to Project 03,
where the same model would be run locally.

Stdlib-only on purpose. The dependency this would add buys nothing here: the
request is one POST with a JSON body, and keeping it out means the runners
import cleanly in an environment that only has the Anthropic SDK.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from harness.runners.base import Completion, RunnerError, timed
from harness.runners.registry import ModelSpec

ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
KEY_VARS = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}

MAX_TOKENS = 4000


class OpenAICompatRunner:
    def __init__(self, spec: ModelSpec, *, timeout: float = 120.0):
        if spec.provider not in ENDPOINTS:
            raise RunnerError(f"no OpenAI-compatible endpoint for {spec.provider!r}")

        self.provider = spec.provider
        self.spec = spec
        # The open-weight slot carries no id until one is chosen, so that the
        # registry never implies a model has been picked or called.
        self.model = spec.model_id or os.environ.get("OPENROUTER_MODEL", "")
        if not self.model:
            raise RunnerError(
                f"no model id for {spec.key!r}; set OPENROUTER_MODEL to the "
                "open-weight model you intend to benchmark"
            )

        self._key = os.environ.get(KEY_VARS[self.provider], "")
        if not self._key:
            raise RunnerError(f"{KEY_VARS[self.provider]} is not set")
        self._url = ENDPOINTS[self.provider]
        self._timeout = timeout

    @timed
    def run(self, prompt: str, *, system: str | None = None) -> Completion:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps(
            {"model": self.model, "max_tokens": MAX_TOKENS, "messages": messages}
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
        )

        blank = Completion(
            text="", model=self.model, provider=self.provider,
            tokens_in=0, tokens_out=0, latency_ms=0,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            blank.error = f"http_{exc.code}: {exc.read()[:200].decode('utf-8', 'replace')}"
            return blank
        except Exception as exc:  # noqa: BLE001 - a failed call is a scored miss
            blank.error = f"{type(exc).__name__}: {exc}"
            return blank

        return parse_response(payload, self.model, self.provider)


def parse_response(payload: dict, model: str, provider: str) -> Completion:
    """Turn a chat-completions body into a Completion.

    Separate from the request so it can be tested without a network call, and
    tolerant of the fields OpenRouter omits for some upstream providers.
    """
    choices = payload.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}

    return Completion(
        text=message.get("content") or "",
        model=payload.get("model") or model,
        provider=provider,
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
        cached_tokens_in=details.get("cached_tokens", 0) or 0,
        latency_ms=0,
        request_id=payload.get("id"),
        stop_reason=(choices[0].get("finish_reason") if choices else None),
        error=None if choices else "empty_response: no choices returned",
    )
