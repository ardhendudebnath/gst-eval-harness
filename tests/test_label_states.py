"""State filtering and spreading in the labelling queue.

Gujarat is 23 of the 31 rulings quoting the abolished slab. Working the queue
in file order would make the rate-changed-2025 finding partly a claim about
Gujarat packaging disputes.
"""

from harness.label.cli import _interleave, _state_of, select_queue


def rec(sid: str, state: str) -> dict:
    return {
        "source": "aar",
        "source_id": sid,
        "input": f"The applicant manufactures product {sid}.",
        "collection_meta": {"state": state, "stale_rates_in_ruling": ["12"]},
    }


POOL = (
    [rec(f"g{i}", "Gujarat") for i in range(8)]
    + [rec("k1", "Karnataka"), rec("t1", "Telangana"), rec("w1", "West Bengal")]
)


def test_exclude_state():
    queue = select_queue(POOL, set(), exclude_state="Gujarat")
    assert {r["source_id"] for r in queue} == {"k1", "t1", "w1"}


def test_exclude_state_is_case_insensitive():
    assert len(select_queue(POOL, set(), exclude_state="gujarat")) == 3


def test_state_selects_only_that_state():
    queue = select_queue(POOL, set(), state="Karnataka")
    assert [r["source_id"] for r in queue] == ["k1"]


def test_state_matches_on_substring():
    # "West Bengal" should be reachable as "bengal".
    assert [r["source_id"] for r in select_queue(POOL, set(), state="bengal")] == ["w1"]


def test_spread_states_breaks_up_the_dominant_run():
    queue = select_queue(POOL, set(), spread_states=True)
    first_three = [_state_of(r) for r in queue[:3]]
    # Without spreading these would all be Gujarat.
    assert len(set(first_three)) == 3


def test_spread_keeps_every_record():
    assert len(select_queue(POOL, set(), spread_states=True)) == len(POOL)


def test_spread_composes_with_exclusion():
    queue = select_queue(POOL, set(), exclude_state="Gujarat", spread_states=True)
    assert {r["source_id"] for r in queue} == {"k1", "t1", "w1"}


def test_state_and_exclude_together_yield_nothing():
    assert select_queue(POOL, set(), state="Gujarat", exclude_state="Gujarat") == []


def test_missing_state_is_grouped_not_dropped():
    pool = POOL + [{"source": "aar", "source_id": "x1", "input": "x", "collection_meta": {}}]
    queue = select_queue(pool, set(), spread_states=True)
    assert "x1" in {r["source_id"] for r in queue}
    assert _state_of({"collection_meta": {}}) == "(unknown)"


def test_interleave_is_stable_within_a_group():
    ordered = _interleave(POOL, _state_of)
    gujarat = [r["source_id"] for r in ordered if _state_of(r) == "Gujarat"]
    assert gujarat == [f"g{i}" for i in range(8)]
