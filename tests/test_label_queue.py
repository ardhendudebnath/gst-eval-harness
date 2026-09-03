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
