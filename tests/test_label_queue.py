"""Queue selection for the labelling tool.

The `--stale 12` path matters most: 12% was abolished on 22 Sep 2025, so a
ruling quoting it is by construction a rate-changed-2025 example, and those are
the slice the headline finding rests on.
"""

from harness.label.cli import select_queue

POOL = [
    {
        "source": "off",
        "source_id": "off-1",
        "input": "Tata Salt, 1 kg",
        "collection_meta": {"categories": "Table salts"},
    },
    {
        "source": "off",
        "source_id": "off-2",
        "input": "Britannia Marie Gold Biscuit, 64 g",
        "collection_meta": {},
    },
    {
        "source": "aar",
        "source_id": "pen-tips.pdf",
        "input": "The Applicant manufactures ball point pen tips and balls.",
        "collection_meta": {"stale_rates_in_ruling": ["12", "18"]},
    },
    {
        "source": "aar",
        "source_id": "quartz.pdf",
        "input": "The applicant manufactures Quartz Slabs (Artificial Stone).",
        "collection_meta": {"stale_rates_in_ruling": ["18"]},
    },
    {
        "source": "aar",
        "source_id": "cryo.pdf",
        "input": "The applicant supplies Cryo Containers made of aluminium.",
        "collection_meta": {},
    },
]


def test_no_filters_returns_everything_unlabelled():
    assert len(select_queue(POOL, set())) == 5


def test_already_labelled_records_are_excluded():
    queue = select_queue(POOL, {"off-1", "cryo.pdf"})
    assert {r["source_id"] for r in queue} == {"off-2", "pen-tips.pdf", "quartz.pdf"}


def test_stale_twelve_selects_only_the_abolished_slab_rulings():
    queue = select_queue(POOL, set(), stale="12")
    assert [r["source_id"] for r in queue] == ["pen-tips.pdf"]


def test_stale_eighteen_selects_a_different_set():
    assert {r["source_id"] for r in select_queue(POOL, set(), stale="18")} == {
        "pen-tips.pdf",
        "quartz.pdf",
    }


def test_stale_ignores_records_with_no_rates_recorded():
    # Missing key and empty list must both behave as "no rates", not match-all.
    assert all(r["source_id"] != "cryo.pdf" for r in select_queue(POOL, set(), stale="12"))


def test_source_filter():
    assert {r["source"] for r in select_queue(POOL, set(), source="aar")} == {"aar"}
    assert len(select_queue(POOL, set(), source="off")) == 2


def test_keyword_filter_is_case_insensitive():
    assert [r["source_id"] for r in select_queue(POOL, set(), keyword="QUARTZ")] == [
        "quartz.pdf"
    ]


def test_filters_compose():
    queue = select_queue(POOL, set(), source="aar", stale="18", keyword="quartz")
    assert [r["source_id"] for r in queue] == ["quartz.pdf"]


def test_filters_that_exclude_everything_return_empty():
    assert select_queue(POOL, set(), source="off", stale="12") == []


def test_stale_filter_does_not_mutate_the_pool():
    select_queue(POOL, set(), stale="12")
    assert len(POOL) == 5


# --- rate-changed candidates ----------------------------------------------

CANDIDATE_POOL = [
    {"source": "off", "source_id": f"b{i}", "input": f"Brand Biscuit {i}, 50 g",
     "collection_meta": {}}
    for i in range(10)
] + [
    {"source": "off", "source_id": "c1", "input": "Cadbury chocolate, 40 g", "collection_meta": {}},
    {"source": "off", "source_id": "n1", "input": "Haldiram bhujia, 200 g", "collection_meta": {}},
    {"source": "off", "source_id": "t1", "input": "Colgate toothpaste, 100 g", "collection_meta": {}},
    {"source": "off", "source_id": "s1", "input": "Tata Salt, 1 kg", "collection_meta": {}},
]


def test_changed_candidates_selects_only_announced_families():
    queue = select_queue(CANDIDATE_POOL, set(), changed_candidates=True)
    ids = {r["source_id"] for r in queue}
    assert "s1" not in ids  # salt is not in a moved family
    assert {"c1", "n1", "t1"} <= ids


def test_changed_candidates_interleaves_families():
    # Ten biscuits sit first in file order. Without interleaving the first four
    # would all be biscuits and the slice would skew.
    queue = select_queue(CANDIDATE_POOL, set(), changed_candidates=True)
    first_four = {r["source_id"] for r in queue[:4]}
    assert len(first_four) == 4
    assert first_four != {"b0", "b1", "b2", "b3"}
    # One from each of the four represented families.
    assert {"c1", "n1", "t1"} <= first_four


def test_interleaving_keeps_every_candidate():
    queue = select_queue(CANDIDATE_POOL, set(), changed_candidates=True)
    assert len(queue) == 13  # all but the salt


def test_changed_candidates_composes_with_source():
    aar = dict(POOL[2])
    queue = select_queue(
        CANDIDATE_POOL + [aar], set(), source="off", changed_candidates=True
    )
    assert all(r["source"] == "off" for r in queue)
