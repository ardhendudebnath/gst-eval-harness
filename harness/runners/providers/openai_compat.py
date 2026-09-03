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
    # NVIDIA's API catalog serves open-weight models over the same wire format.
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
}
KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}
MODEL_VARS = {"openrouter": "OPENROUTER_MODEL", "nvidia": "NVIDIA_MODEL"}

#: Headroom for reasoning. Nemotron-style models emit their chain into a
#: separate `reasoning_content` field that still bills as output tokens, so a
#: classification-sized budget truncates the answer that follows it.
MAX_TOKENS = 4000
MAX_TOKENS_THINKING = 16384


class OpenAICompatRunner:
    def __init__(
        self,
        spec: ModelSpec,
        *,
        timeout: float = 300.0,
        thinking: bool = True,
    ):
        if spec.provider not in ENDPOINTS:
            raise RunnerError(f"no OpenAI-compatible endpoint for {spec.provider!r}")

        self.provider = spec.provider
        self.spec = spec
        # A slot may carry no id until one is chosen, so the registry never
        # implies a model has been picked or called.
        env_var = MODEL_VARS.get(spec.provider, "")
        self.model = spec.model_id or (os.environ.get(env_var, "") if env_var else "")
        if not self.model:
            raise RunnerError(
                f"no model id for {spec.key!r}; set {env_var or 'the model id'} "
                "to the model you intend to benchmark"
            )

        self._key = os.environ.get(KEY_VARS[self.provider], "")
        if not self._key:
            raise RunnerError(f"{KEY_VARS[self.provider]} is not set")
        self._url = ENDPOINTS[self.provider]
        self._timeout = timeout
        # On by default: Claude models think adaptively unless told otherwise,
        # so leaving reasoning off here would compare a thinking model against
        # a non-thinking one. Recorded on every completion either way.
        self.thinking = thinking

    @timed
    def run(self, prompt: str, *, system: str | None = None) -> Completion:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "max_tokens": MAX_TOKENS_THINKING if self.thinking else MAX_TOKENS,
            "messages": messages,
        }
        if self.provider == "nvidia" and self.thinking:
            # Nemotron-family reasoning switch. Harmless on models that ignore
            # it; the served model id in the response records what actually ran.
            payload["chat_template_kwargs"] = {"enable_thinking": True}

        body = json.dumps(payload).encode("utf-8")
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

        completion = parse_response(response, self.model, self.provider)
        completion.extra["thinking"] = self.thinking
        return completion


def parse_response(payload: dict, model: str, provider: str) -> Completion:
    """Turn a chat-completions body into a Completion.

    Separate from the request so it can be tested without a network call, and
    tolerant of the fields some upstream providers omit.

    Reasoning is deliberately **not** merged into `text`. Models that reason
    return it in a separate `reasoning_content` field, and folding it into the
    answer would feed the chain of thought to a parser looking for `SLAB:` —
    which matches whichever rate the model considered first rather than the one
    it concluded with. Its length is recorded so the tokens are accounted for.
    """
    choices = payload.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}

    reasoning = message.get("reasoning_content") or ""
    extra: dict = {}
    if reasoning:
        extra["reasoning_chars"] = len(reasoning)

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
        extra=extra,
    )
