"""The eval driver, exercised end to end with a stubbed runner.

`run_one` is the one place the whole chain meets — dataset, prompt, provider,
parse, score, cost, result file. It had no coverage, which is exactly the kind
of gap that surfaces after someone has spent money on a real run.

No network. A stub runner returns canned replies so the wiring is what gets
tested, not a model.
"""

import json

import pytest

from harness.run import load_dataset, run_one
from harness.runners.base import Completion
from harness.schema import Example, append_jsonl


class StubRunner:
    """Replays canned replies in order, then repeats the last one."""

    provider = "stub"
    model = "stub-model-1"

    def __init__(self, replies, *, fail_on=()):
        self.replies = list(replies)
        self.fail_on = set(fail_on)
        self.calls = 0
        self.prompts = []
        self.systems = []

    def run(self, prompt, *, system=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        i = self.calls
        self.calls += 1
        if i in self.fail_on:
            return Completion(
                text="", model=self.model, provider=self.provider,
                tokens_in=0, tokens_out=0, latency_ms=5,
                error="http_500: upstream exploded",
            )
        reply = self.replies[min(i, len(self.replies) - 1)]
        return Completion(
            text=reply, model=self.model, provider=self.provider,
            tokens_in=600, tokens_out=150, latency_ms=800,
        )


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Three gold rows: a plain one, an unanswerable one, and a moved rate."""
    golden = tmp_path / "golden.jsonl"
    rows = [
        Example(id="gst-0001", input="Portland cement, 50 kg bag", slab="18",
                hsn4="2523", answerable=True, justification="Sch II",
                difficulty="typical"),
        Example(id="gst-0002", input="Royal Enfield motorcycle, black",
                slab="UNANSWERABLE", hsn4="8711", answerable=False,
                justification="cc unstated", difficulty="out_of_scope",
                labeller_notes="reason=rate-fact-absent; missing=cc"),
        Example(id="gst-0003", input="Thums Up, 250 ml", slab="40", hsn4="2202",
                answerable=True, justification="Sch III", difficulty="hard"),
    ]
    append_jsonl(golden, rows)
    monkeypatch.setattr("harness.run.GOLDEN", golden)
    monkeypatch.setattr("harness.report.results.GOLDEN", golden)
    return golden


def install(monkeypatch, runner):
    monkeypatch.setattr("harness.run.build", lambda key, **kw: runner)


def test_dataset_loads_and_limits(dataset):
    assert len(load_dataset()) == 3
    assert len(load_dataset(limit=2)) == 2


def test_full_chain_produces_a_scored_result(dataset, tmp_path, monkeypatch):
    runner = StubRunner([
        "SLAB: 18\nHSN: 2523\nANSWERABLE: yes\nWHY: Cement, Schedule II.",
        "SLAB: UNANSWERABLE\nHSN: 8711\nANSWERABLE: no\nWHY: cc not stated.",
        "SLAB: 40\nHSN: 2202\nANSWERABLE: yes\nWHY: Aerated, Schedule III.",
    ])
    install(monkeypatch, runner)
    monkeypatch.setattr("harness.report.results.RESULTS", tmp_path)
    monkeypatch.chdir(tmp_path)

    result = run_one("opus-5", load_dataset(), mode="shared", sleep=0)

    assert result is not None
    assert runner.calls == 3
    assert result.summary["slab_acc"] == 1.0
    assert result.summary["stale_slab_rate"] == 0.0
    assert result.cost["correct"] == 3
    assert len(result.rows) == 3


def test_the_goods_reach_the_prompt(dataset, tmp_path, monkeypatch):
    runner = StubRunner(["SLAB: 18\nHSN: 2523"])
    install(monkeypatch, runner)
    monkeypatch.chdir(tmp_path)
    run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    assert "Portland cement" in runner.prompts[0]
    assert runner.systems[0]  # the system prompt is sent


def test_an_abolished_answer_is_recorded_as_stale(dataset, tmp_path, monkeypatch):
    # The finding: a model reciting the pre-2025 table on cement.
    install(monkeypatch, StubRunner(["SLAB: 28\nHSN: 2523\nANSWERABLE: yes\nWHY: 28%."]))
    monkeypatch.chdir(tmp_path)
    result = run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    assert result.summary["slab_acc"] == 0.0
    assert result.summary["stale_slab_rate"] == 1.0
    assert result.summary["stale_by_slab"] == {"28": 1}
    assert result.rows[0]["stale_slab"] == "28"


def test_a_failed_call_scores_wrong_and_is_recorded(dataset, tmp_path, monkeypatch):
    install(monkeypatch, StubRunner(["SLAB: 18\nHSN: 2523"], fail_on=[0]))
    monkeypatch.chdir(tmp_path)
    result = run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    assert result.summary["errored"] == 1
    assert result.summary["slab_acc"] == 0.0
    assert "http_500" in result.rows[0]["error"]


def test_an_unparseable_reply_is_not_silently_dropped(dataset, tmp_path, monkeypatch):
    install(monkeypatch, StubRunner(["I'd say roughly eighteen percent."]))
    monkeypatch.chdir(tmp_path)
    result = run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    assert result.summary["unparseable"] == 1
    assert result.summary["n"] == 1  # counted, not skipped


def test_result_records_provenance(dataset, tmp_path, monkeypatch):
    install(monkeypatch, StubRunner(["SLAB: 18\nHSN: 2523"]))
    monkeypatch.chdir(tmp_path)
    result = run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    assert result.model_id == "claude-opus-5"
    assert result.served_model_id == "stub-model-1"  # what actually answered
    assert result.prompt_mode == "shared"
    assert result.dataset_sha and result.dataset_n == 3
    assert result.started_at and result.finished_at


def test_result_is_written_and_reloads(dataset, tmp_path, monkeypatch):
    install(monkeypatch, StubRunner(["SLAB: 18\nHSN: 2523"]))
    monkeypatch.chdir(tmp_path)
    run_one("opus-5", load_dataset(limit=1), mode="shared", sleep=0)

    written = list((tmp_path / "results").glob("*.json"))
    assert len(written) == 1
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["model_key"] == "opus-5"
    assert data["summary"]["n"] == 1


def test_a_runner_that_cannot_be_built_is_skipped_not_fatal(dataset, monkeypatch, capsys):
    from harness.runners import RunnerError

    def boom(key, **kw):
        raise RunnerError("NVIDIA_API_KEY is not set")

    monkeypatch.setattr("harness.run.build", boom)
    assert run_one("open-weight", load_dataset(), mode="shared", sleep=0) is None
    assert "NVIDIA_API_KEY" in capsys.readouterr().out


def test_dry_run_estimate_marks_unpriced_models(capsys):
    from harness.run import estimate

    estimate(["opus-5", "open-weight"], 20)
    out = capsys.readouterr().out
    assert "no API calls made" in out
    assert "unpriced" in out
