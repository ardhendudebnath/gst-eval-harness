"""Runner plumbing and cost accounting.

No test here makes a network call. What is asserted is the accounting: prices
carry a date, an unpriced model produces no number, and a run with no correct
answers does not divide by zero.
"""

import pytest

from harness.report.cost import build as build_cost
from harness.runners import MODELS, build, get, priced
from harness.runners.base import Completion, RunnerError
from harness.runners.providers.openai_compat import parse_response
from harness.runners.registry import FX_READ_ON, PRICES_READ_ON


def comp(tin=1000, tout=200, ms=500, **kw) -> Completion:
    return Completion(
        text="SLAB: 18", model="m", provider="p",
        tokens_in=tin, tokens_out=tout, latency_ms=ms, **kw
    )


# --- registry -------------------------------------------------------------


def test_every_tier_the_plan_asks_for_is_present():
    tiers = {m.tier for m in MODELS.values()}
    assert {"frontier", "mid", "small", "open-weight"} <= tiers


def test_no_model_id_carries_an_invented_date_suffix():
    import re

    for m in MODELS.values():
        if m.model_id:
            assert not re.search(r"-20\d{6}$", m.model_id), m.model_id


def test_nothing_is_marked_verified_before_it_has_been_called():
    # The plan: never name a model you have not actually called.
    assert not any(m.verified for m in MODELS.values())


def test_prices_and_fx_are_dated():
    assert PRICES_READ_ON and FX_READ_ON


def test_open_weight_slot_is_unpriced_until_a_price_is_read():
    assert not priced(get("open-weight"))


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        get("no-such-model")


def test_cost_scales_with_tokens():
    spec = get("opus-5")
    assert spec.cost_usd(1_000_000, 0) == pytest.approx(5.00)
    assert spec.cost_usd(0, 1_000_000) == pytest.approx(25.00)


# --- cost report ----------------------------------------------------------


def test_cost_per_correct_answer():
    spec = get("opus-5")
    # 1M in + 1M out = $30 across 10 completions, 6 correct.
    cs = [comp(tin=100_000, tout=100_000) for _ in range(10)]
    r = build_cost(spec, cs, correct=6)
    assert r.usd_total == pytest.approx(30.0)
    assert r.usd_per_correct == pytest.approx(5.0)
    assert r.inr_per_correct == pytest.approx(5.0 * 88.0)


def test_unpriced_model_reports_no_cost_and_says_why():
    r = build_cost(get("open-weight"), [comp()], correct=1)
    assert r.usd_total is None and r.usd_per_correct is None
    assert r.unpriced_reason


def test_zero_correct_does_not_divide_by_zero():
    r = build_cost(get("opus-5"), [comp()], correct=0)
    assert r.usd_total is not None
    assert r.usd_per_correct is None
    assert "undefined" in r.unpriced_reason


def test_report_carries_the_price_date():
    assert build_cost(get("opus-5"), [comp()], correct=1).as_row()["prices_read_on"]


def test_latency_percentiles_are_observed_values():
    cs = [comp(ms=v) for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]]
    r = build_cost(get("opus-5"), cs, correct=1)
    assert r.p50_latency_ms in (50, 60)
    assert r.p95_latency_ms == 100  # nearest-rank, never interpolated


def test_failed_calls_still_count_their_tokens():
    cs = [comp(), comp(tin=50, tout=0, error="http_500: boom")]
    r = build_cost(get("opus-5"), cs, correct=1)
    assert r.calls == 2
    assert r.tokens_in == 1050


# --- openai-compatible response parsing -----------------------------------


def test_parses_a_chat_completions_body():
    c = parse_response(
        {
            "id": "chatcmpl-1",
            "model": "some/open-model",
            "choices": [{"message": {"content": "SLAB: 5"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 8},
        },
        "requested-model", "openrouter",
    )
    assert c.text == "SLAB: 5"
    assert c.model == "some/open-model"  # what actually served it
    assert c.tokens_in == 120 and c.tokens_out == 8
    assert c.ok


def test_empty_choices_is_an_error_not_a_blank_answer():
    c = parse_response({"usage": {}}, "m", "openrouter")
    assert not c.ok and "empty_response" in c.error


def test_missing_usage_does_not_crash():
    c = parse_response(
        {"choices": [{"message": {"content": "hi"}}]}, "m", "openrouter"
    )
    assert c.tokens_in == 0


# --- construction ---------------------------------------------------------


def test_missing_api_key_refuses_clearly(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(RunnerError, match="NVIDIA_API_KEY"):
        build("open-weight")


# --- the open-weight tier -------------------------------------------------


def test_open_weight_entry_has_a_published_container():
    # The plan asks for one you could self-host. A pullable image and a
    # documented run command is evidence; a parameter count is an inference.
    spec = get("open-weight")
    assert spec.nim_image.startswith("nvcr.io/nim/")
    assert spec.tier == "open-weight"


def test_the_same_model_is_registered_hosted_and_local():
    # Identical model, identical wire format, different base URL. That is the
    # bridge to project 03 — the row can be reproduced on your own GPU.
    hosted, local = get("open-weight"), get("open-weight-local")
    assert hosted.model_id == local.model_id
    assert hosted.nim_image == local.nim_image
    assert local.provider == "nim"


def test_the_550b_is_an_extra_not_the_open_weight_entry():
    # Open weights, but nobody self-hosts 550B, so it cannot discharge the
    # requirement — it is a separate optional comparison.
    assert get("open-weight-xl").model_id != get("open-weight").model_id
    assert "not self-hostable" in get("open-weight-xl").note


@pytest.mark.parametrize(
    "key", ["open-weight", "open-weight-local", "open-weight-lite", "open-weight-xl"]
)
def test_open_weight_models_are_unpriced_until_a_price_is_read(key):
    # A fabricated price silently reorders the ranking that
    # cost-per-correct-answer exists to produce.
    assert not priced(get(key))


def test_local_nim_needs_no_api_key(monkeypatch):
    from harness.runners.providers.openai_compat import KEY_VARS

    assert KEY_VARS["nim"] == ""


def test_local_nim_url_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("NIM_BASE_URL", "http://gpu-box:9000")
    r = build("open-weight-local")
    assert r._url == "http://gpu-box:9000/v1/chat/completions"


def test_local_nim_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("NIM_BASE_URL", raising=False)
    assert build("open-weight-local")._url.startswith("http://localhost:8000")


# --- reasoning switches are not interchangeable ---------------------------


def test_each_family_gets_its_own_switch():
    from harness.runners.providers.openai_compat import apply_reasoning

    chat: dict = {"messages": []}
    apply_reasoning(chat, "chat_template", True)
    assert chat["chat_template_kwargs"] == {"enable_thinking": True}

    effort: dict = {"messages": []}
    apply_reasoning(effort, "effort", True)
    assert effort["reasoning_effort"] == "max"


def test_system_toggle_leads_the_conversation():
    # The model's documented prompt format puts it first; buried later it is
    # silently ignored and the run would claim reasoning it never did.
    from harness.runners.providers.openai_compat import apply_reasoning

    payload = {"messages": [{"role": "user", "content": "classify this"}]}
    apply_reasoning(payload, "system_toggle", True)
    assert payload["messages"][0] == {
        "role": "system", "content": "detailed thinking on"
    }
    assert payload["messages"][-1]["content"] == "classify this"


def test_system_toggle_off_says_off():
    from harness.runners.providers.openai_compat import apply_reasoning

    payload = {"messages": []}
    apply_reasoning(payload, "system_toggle", False)
    assert payload["messages"][0]["content"] == "detailed thinking off"


def test_no_style_adds_nothing():
    from harness.runners.providers.openai_compat import apply_reasoning

    payload = {"messages": [{"role": "user", "content": "x"}]}
    apply_reasoning(payload, "", True)
    assert payload == {"messages": [{"role": "user", "content": "x"}]}


def test_every_open_weight_model_declares_its_switch():
    for key in ("open-weight", "open-weight-local", "open-weight-lite", "open-weight-xl"):
        assert get(key).reasoning_style, f"{key} has no reasoning_style"


def test_nvidia_endpoint_is_the_catalog():
    from harness.runners.providers.openai_compat import ENDPOINTS

    assert ENDPOINTS["nvidia"] == "https://integrate.api.nvidia.com/v1/chat/completions"


# --- reasoning models -----------------------------------------------------


def test_reasoning_is_not_merged_into_the_answer():
    # Folding the chain of thought into the text would feed the parser
    # whichever rate the model considered first, not the one it concluded with.
    c = parse_response(
        {
            "choices": [{
                "message": {
                    "content": "SLAB: 18\nHSN: 9608",
                    "reasoning_content": "Maybe SLAB: 12? No, that is abolished.",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 500, "completion_tokens": 900},
        },
        "nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia",
    )
    assert c.text == "SLAB: 18\nHSN: 9608"
    assert "12" not in c.text

    from harness.prompt import parse

    assert parse(c.text).slab == "18"


def test_reasoning_length_is_recorded_so_tokens_are_accounted_for():
    c = parse_response(
        {
            "choices": [{"message": {"content": "SLAB: 5", "reasoning_content": "x" * 40}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 60},
        },
        "m", "nvidia",
    )
    assert c.extra["reasoning_chars"] == 40
    assert c.tokens_out == 60  # reasoning bills as output


def test_no_reasoning_field_is_fine():
    c = parse_response(
        {"choices": [{"message": {"content": "SLAB: 5"}}], "usage": {}}, "m", "nvidia"
    )
    assert "reasoning_chars" not in c.extra


def test_completion_ok_flag():
    assert comp().ok
    assert not comp(error="boom").ok
