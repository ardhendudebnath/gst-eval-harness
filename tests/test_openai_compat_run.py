"""The OpenAI-compatible runner's `run()` method, over a faked socket.

Every other test in this repo calls `parse_response` directly. That left the
request-building and response-handling path — the part that actually runs when
you spend money — with no coverage at all, and it was hiding a NameError that
fired on every *successful* call.

`urlopen` is replaced, so no network. What's under test is the wiring: does the
request carry the right body, and does a 200 come back as a Completion.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from harness.runners.providers import openai_compat as oc
from harness.runners.registry import get


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def fake_urlopen(body: dict, captured: list):
    def _open(req, timeout=None):
        captured.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "body": json.loads(req.data.decode("utf-8")),
        })
        return FakeHTTPResponse(json.dumps(body).encode("utf-8"))
    return _open


def reply(content="SLAB: 18\nHSN: 2523", *, reasoning="", model="served/model-x"):
    message = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {
        "id": "cmpl-abc123",
        "model": model,
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 640, "completion_tokens": 210},
    }


@pytest.fixture
def nvidia(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-not-a-real-key")
    return get("open-weight")


def test_a_successful_call_returns_a_completion(nvidia, monkeypatch):
    """The regression. This raised NameError: name 'response' is not defined."""
    captured = []
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake_urlopen(reply(), captured))

    completion = oc.OpenAICompatRunner(nvidia).run("Cement?", system="You classify.")

    assert completion.ok
    assert completion.text == "SLAB: 18\nHSN: 2523"
    assert completion.model == "served/model-x"  # what answered, not what we asked for
    assert completion.tokens_in == 640 and completion.tokens_out == 210
    assert completion.request_id == "cmpl-abc123"
    assert completion.latency_ms >= 0


def test_the_request_body_is_what_we_think_it_is(nvidia, monkeypatch):
    captured = []
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake_urlopen(reply(), captured))
    oc.OpenAICompatRunner(nvidia).run("Cement?", system="You classify.")

    sent = captured[0]
    assert sent["url"] == oc.ENDPOINTS["nvidia"]
    assert sent["headers"]["Authorization"] == "Bearer nvapi-test-not-a-real-key"
    assert sent["body"]["model"] == nvidia.model_id
    assert sent["body"]["max_tokens"] == oc.MAX_TOKENS_THINKING
    # chat_template: Nemotron 3.x takes the switch as a template kwarg, and
    # our own system prompt stays first in the conversation.
    assert sent["body"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert sent["body"]["messages"][0]["content"] == "You classify."
    assert sent["body"]["messages"][1]["content"] == "Cement?"


def test_reasoning_off_changes_the_wire_and_the_budget(nvidia, monkeypatch):
    captured = []
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake_urlopen(reply(), captured))
    c = oc.OpenAICompatRunner(nvidia, thinking=False).run("Cement?")

    assert captured[0]["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured[0]["body"]["max_tokens"] == oc.MAX_TOKENS
    assert c.extra["thinking"] is False  # recorded, so a result can't misreport it


def test_the_system_toggle_style_still_leads_the_conversation(monkeypatch):
    """No model in the registry uses this today — the retired
    llama-3.3-nemotron-super-49b did — but apply_reasoning still supports it,
    and an unsupported switch is ignored rather than rejected, so a model
    would run with reasoning off while the result claimed it was on."""
    from harness.runners.registry import ModelSpec

    spec = ModelSpec(key="probe", model_id="vendor/toggle-model", provider="nvidia",
                     tier="open-weight", usd_in_per_m=0.0, usd_out_per_m=0.0,
                     reasoning_style="system_toggle")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-not-a-real-key")
    captured = []
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake_urlopen(reply(), captured))

    oc.OpenAICompatRunner(spec).run("Cement?", system="You classify.")

    assert captured[0]["body"]["messages"][0] == {
        "role": "system", "content": "detailed thinking on"
    }
    assert "chat_template_kwargs" not in captured[0]["body"]


def test_reasoning_stays_out_of_the_scored_text(nvidia, monkeypatch):
    """The assumption the whole open-weight row rests on, never yet seen live.

    If a model returned its chain inline instead, `text` would lead with the
    reasoning and the parser would match the first rate it considered.
    """
    monkeypatch.setattr(
        oc.urllib.request, "urlopen",
        fake_urlopen(reply(reasoning="Could be 28%... no, 19/2025 omits Sch VII."), []),
    )
    c = oc.OpenAICompatRunner(nvidia).run("Cement?")

    assert c.text == "SLAB: 18\nHSN: 2523"
    assert "28%" not in c.text
    assert c.extra["reasoning_chars"] > 0


def test_an_http_error_is_captured_not_raised(nvidia, monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 429, "Too Many Requests", {},
            io.BytesIO(b'{"error":"rate limit"}'),
        )

    monkeypatch.setattr(oc.urllib.request, "urlopen", boom)
    c = oc.OpenAICompatRunner(nvidia).run("Cement?")

    assert not c.ok and c.text == ""
    assert c.error.startswith("http_429") and "rate limit" in c.error


def test_a_timeout_is_captured_not_raised(nvidia, monkeypatch):
    def boom(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(oc.urllib.request, "urlopen", boom)
    c = oc.OpenAICompatRunner(nvidia).run("Cement?")

    assert not c.ok and "TimeoutError" in c.error


def test_a_local_nim_gets_no_bearer_token(monkeypatch):
    captured = []
    monkeypatch.setenv("NIM_BASE_URL", "http://localhost:8000")
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake_urlopen(reply(), captured))
    runner = oc.OpenAICompatRunner(get("open-weight-local"))
    assert runner._url == "http://localhost:8000/v1/chat/completions"

    runner.run("Cement?")
    assert "Authorization" not in captured[0]["headers"]


def test_a_missing_key_is_refused_before_any_call(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(oc.RunnerError, match="NVIDIA_API_KEY"):
        oc.OpenAICompatRunner(get("open-weight"))
