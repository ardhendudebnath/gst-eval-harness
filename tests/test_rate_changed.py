"""Candidate detection for the rate-changed-2025 slice.

This module suggests where to look; it must never be mistaken for deciding
whether a rate moved. The tests below pin both halves of that: it finds the
families announced as moving, and it does not pretend to know more than that.
"""

import pytest

from harness.collect.rate_changed import (
    RATE_CHANGED_FAMILIES,
    candidate_families,
    is_candidate,
    record_candidate_families,
)


@pytest.mark.parametrize(
    "text,family",
    [
        ("Colgate Strong Teeth Toothpaste 200g", "toothpaste"),
        ("Dabur Amla Hair Oil 100 ml", "hair oil"),
        ("Clinic Plus Shampoo sachet", "shampoo"),
        ("Amul Butter 500 g", "butter and ghee"),
        ("Haldiram Aloo Bhujia 200 g", "namkeen"),
        ("Maggi 2-Minute Noodles 70 g", "pasta and noodles"),
        ("Cadbury Dairy Milk chocolate", "chocolate"),
        ("Kelloggs Corn Flakes 475 g", "cereal preparations"),
        ("Britannia Marie Gold Biscuit 64 g", "biscuits"),
        ("Kissan Tomato Ketchup 500 g", "sauces"),
    ],
)
def test_announced_families_are_recognised(text, family):
    assert family in candidate_families(text)


@pytest.mark.parametrize(
    "text",
    [
        "Tata Salt Iodised 1 kg",
        "Aashirvaad Whole Wheat Atta 5 kg",
        "Surf Excel detergent powder 1 kg",
    ],
)
def test_unrelated_listings_are_not_candidates(text):
    assert not is_candidate(text)


def test_word_boundaries_prevent_substring_matches():
    # "sev" inside "several", "oats" inside "coats", "cocoa" is genuine.
    assert not is_candidate("several assorted items")
    assert not is_candidate("raincoats and jackets")
    assert "chocolate" in candidate_families("cocoa powder 100 g")


def test_plurals_match():
    assert "biscuits" in candidate_families("assorted biscuits")
    assert "sauces" in candidate_families("tomato sauces")


def test_category_metadata_is_searched_not_only_the_listing():
    # "Amul, 500 g" names no family; its catalogue category does.
    record = {
        "input": "Amul, 500 g",
        "collection_meta": {"categories": "Butters, Dairy spreads"},
    }
    assert "butter and ghee" in record_candidate_families(record)


def test_record_with_no_signal_returns_empty():
    record = {"input": "Tata Salt, 1 kg", "collection_meta": {"categories": "Table salts"}}
    assert record_candidate_families(record) == []


def test_a_match_is_only_a_candidate():
    # The module deliberately exposes no function that returns a rate, an old
    # rate, or a boolean "moved". Establishing that is the annotator's job.
    import harness.collect.rate_changed as mod

    exported = {n for n in dir(mod) if not n.startswith("_")}
    for forbidden in ("new_rate", "old_rate", "slab_for", "did_move", "rate_moved"):
        assert forbidden not in exported


def test_every_family_has_at_least_one_search_term():
    assert all(terms for terms in RATE_CHANGED_FAMILIES.values())
