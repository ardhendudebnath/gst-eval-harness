"""Aggregating repeated probe runs.

A single run of this probe carries run-to-run noise the same size as the
finding it reports, so the spread is the point, not a footnote.
"""

from __future__ import annotations

from harness.probe import aggregate
from harness.schema import Example


def ref(eid, slab):
    return (Example(id=eid, input="x", slab=slab, hsn4="6815", answerable=True,
                    justification="", difficulty="typical"), {})


REFS = [ref("gst-0001", "18"), ref("gst-0002", "5"), ref("gst-0003", "18")]


def run(n, answers, slab_acc, stale=0.0, cited=0.0):
    return {
        "run": n,
        "summary": {"slab_acc": slab_acc, "hsn_acc": 0.5,
                    "stale_slab_rate": stale, "stale_cited_rate": cited,
                    "abstention_acc": 1.0},
        "rows": [{"id": eid, "predicted_slab": a}
                 for eid, a in zip(("gst-0001", "gst-0002", "gst-0003"), answers)],
    }


def test_mean_and_range_are_reported_per_metric():
    agg = aggregate([
        run(1, ["18", "5", "18"], 1.0, cited=0.0),
        run(2, ["18", "5", "5"], 2 / 3, cited=0.5),
        run(3, ["12", "5", "18"], 2 / 3, cited=0.25),
    ], REFS)

    slab = agg["metrics"]["slab_acc"]
    assert slab["max"] == 1.0
    assert round(slab["min"], 2) == 0.67
    assert round(slab["range"], 2) == 0.33
    assert len(slab["runs"]) == 3
    assert agg["metrics"]["stale_cited_rate"]["max"] == 0.5


def test_self_agreement_counts_examples_answered_identically():
    agg = aggregate([
        run(1, ["18", "5", "18"], 1.0),
        run(2, ["18", "5", "5"], 2 / 3),
        run(3, ["18", "5", "18"], 1.0),
    ], REFS)

    sa = agg["self_agreement"]
    assert sa["examples"] == 3
    assert sa["answered_identically_every_run"] == 2   # 0001 and 0002
    assert sa["unstable"] == 1
    assert round(sa["rate"], 4) == round(2 / 3, 4)
    assert sa["detail"][0]["id"] == "gst-0003"
    assert sa["detail"][0]["answers"] == ["18", "5", "18"]


def test_a_perfectly_stable_model_reports_no_spread():
    runs = [run(i, ["18", "5", "18"], 1.0) for i in range(1, 4)]
    agg = aggregate(runs, REFS)
    assert agg["metrics"]["slab_acc"]["range"] == 0.0
    assert agg["self_agreement"]["rate"] == 1.0
    assert agg["self_agreement"]["detail"] == []


def test_majority_vote_beats_a_single_unlucky_run():
    """Two runs right, one wrong: the plurality is still right."""
    agg = aggregate([
        run(1, ["18", "5", "18"], 1.0),
        run(2, ["12", "5", "18"], 2 / 3),
        run(3, ["18", "5", "18"], 1.0),
    ], REFS)
    assert agg["majority_vote_slab_acc"] == 1.0


def test_majority_vote_does_not_rescue_a_model_that_is_just_wrong():
    agg = aggregate([
        run(1, ["5", "5", "5"], 1 / 3),
        run(2, ["5", "5", "5"], 1 / 3),
        run(3, ["5", "5", "5"], 1 / 3),
    ], REFS)
    # Only gst-0002 (gold 5%) is right, in every run and in the vote.
    assert round(agg["majority_vote_slab_acc"], 4) == round(1 / 3, 4)


def test_a_single_run_aggregates_without_dividing_by_zero():
    agg = aggregate([run(1, ["18", "5", "18"], 1.0)], REFS)
    assert agg["runs"] == 1
    assert agg["metrics"]["slab_acc"]["range"] == 0.0
    assert agg["self_agreement"]["rate"] == 1.0
