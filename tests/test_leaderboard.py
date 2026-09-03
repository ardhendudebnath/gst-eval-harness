"""Results storage and the leaderboard renderer.

The behaviours that matter: an empty leaderboard says no model was run rather
than showing zeros, ranking is by cost per correct answer rather than accuracy,
and a run scored against an older dataset is flagged instead of being silently
ranked alongside fresh ones.
"""

import json

import pytest

from harness.report.leaderboard import _rank, render
from harness.report.results import (
    RunResult,
    dataset_fingerprint,
    latest_per_model,
    load_all,
    new_run_id,
)


def make(key="opus-5", *, acc=0.8, inr=1.0, stale=0.1, sha="abc", when="2026-09-04",
         mode="shared", tier="frontier") -> RunResult:
    return RunResult(
        run_id=f"{when}_{key}_{mode}",
        model_key=key,
        model_id=f"claude-{key}",
        served_model_id=f"claude-{key}",
        provider="anthropic",
        tier=tier,
        prompt_version="v1",
        prompt_mode=mode,
        dataset_sha=sha,
        dataset_n=400,
        started_at=f"{when}T10:00:00+00:00",
        finished_at=f"{when}T10:30:00+00:00",
        summary={
            "slab_acc": acc, "hsn_acc": 0.6, "abstain_f1": 0.5,
            "stale_slab_rate": stale, "stale_by_slab": {"12": 3}, "errored": 0,
        },
        cost={"inr_per_correct": inr, "usd_total": 2.0, "p50_latency_ms": 900},
    )


# --- empty state ----------------------------------------------------------


def test_empty_leaderboard_says_no_model_was_run():
    out = render([], "", 0)
    assert "No model has been run yet" in out
    # A table of zeros would imply models ran and scored badly.
    assert "<table>" not in out


def test_empty_dataset_is_stated_not_implied():
    assert "Golden set is empty" in render([], "", 0)


# --- ranking --------------------------------------------------------------


def test_ranked_by_cost_per_correct_not_accuracy():
    # The plan's point: 84% at ₹0.30 beats 89% at ₹2.10.
    cheap = make("haiku-4-5", acc=0.84, inr=0.30)
    accurate = make("opus-5", acc=0.89, inr=2.10)
    assert [r.model_key for r in _rank([accurate, cheap])] == ["haiku-4-5", "opus-5"]


def test_unpriced_runs_rank_last_by_accuracy():
    priced = make("opus-5", acc=0.5, inr=1.0)
    unpriced_good = make("open-weight", acc=0.9, inr=None)
    unpriced_bad = make("other", acc=0.2, inr=None)
    order = [r.model_key for r in _rank([unpriced_bad, unpriced_good, priced])]
    assert order == ["opus-5", "open-weight", "other"]


# --- rendering ------------------------------------------------------------


def test_row_shows_the_headline_columns():
    out = render([make(acc=0.842, stale=0.153)], "abc", 400)
    assert "84.2%" in out
    assert "15.3%" in out
    assert "Stale-slab" in out


def test_stale_breakdown_names_the_abolished_rate():
    assert "12%×3" in render([make()], "abc", 400)


def test_stale_dataset_is_flagged():
    out = render([make(sha="old")], "current", 400)
    assert "stale dataset" in out


def test_matching_dataset_is_not_flagged():
    assert "stale dataset" not in render([make(sha="same")], "same", 400)


def test_served_model_id_is_shown():
    run = make()
    run.served_model_id = "claude-opus-5-served"
    assert "claude-opus-5-served" in render([run], "abc", 400)


def test_model_key_is_escaped():
    assert "<script>" not in render([make(key="<script>")], "abc", 400)


def test_footer_carries_the_price_date():
    from harness.runners.registry import PRICES_READ_ON

    assert PRICES_READ_ON in render([make()], "abc", 400)


# --- results storage ------------------------------------------------------


def test_save_and_load_round_trip(tmp_path):
    run = make()
    path = run.save(tmp_path)
    assert RunResult.load(path).to_json() == run.to_json()


def test_load_all_is_newest_first(tmp_path):
    make(key="a", when="2026-01-01").save(tmp_path)
    make(key="b", when="2026-06-01").save(tmp_path)
    assert [r.model_key for r in load_all(tmp_path)] == ["b", "a"]


def test_latest_per_model_keeps_one_row_per_model(tmp_path):
    old = make(key="opus-5", when="2026-01-01", acc=0.5)
    new = make(key="opus-5", when="2026-06-01", acc=0.9)
    picked = latest_per_model([new, old])
    assert len(picked) == 1
    assert picked[0].summary["slab_acc"] == 0.9


def test_tuned_runs_are_not_mixed_into_the_shared_table():
    shared = make(key="opus-5", mode="shared")
    tuned = make(key="opus-5", mode="tuned")
    assert [r.prompt_mode for r in latest_per_model([tuned, shared])] == ["shared"]


def test_run_id_carries_model_and_mode():
    rid = new_run_id("opus-5", "tuned")
    assert "opus-5" in rid and "tuned" in rid


def test_fingerprint_of_a_missing_dataset(tmp_path):
    assert dataset_fingerprint(tmp_path / "nope.jsonl") == ("", 0)


def test_fingerprint_changes_with_content(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text('{"a":1}\n', encoding="utf-8")
    first = dataset_fingerprint(p)
    p.write_text('{"a":2}\n', encoding="utf-8")
    assert dataset_fingerprint(p)[0] != first[0]
    assert dataset_fingerprint(p)[1] == 1


def test_corrupt_result_file_raises_with_the_path(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.json"):
        load_all(tmp_path)
