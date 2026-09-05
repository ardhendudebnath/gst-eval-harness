"""Immovable property is not a classification question.

TN/26/AAR/2021 asked whether GST is payable on a transfer of leasehold rights.
It carried category 97(2)(a), so the clause test admitted it, and the services
screen has no vocabulary for land — so a ruling with no goods, no heading and
no rate reached the corpus and was published.

Every brief below is real, shortened.
"""

from __future__ import annotations

import pytest

from harness.collect.aar import (
    is_about_immovable_property,
    is_about_services,
    is_classification,
)


def row(brief, category="97(2)(a)"):
    return {"brief": brief, "category": category}


@pytest.mark.parametrize("brief", [
    "As to whether GST is payable on the transfer of leasehold rights in "
    "respect of the consideration of Rs. 15 Crores received for the land "
    "allotted by SIPCOT?",
    "Whether selling of residential flats after date of completion certificate "
    "of commercial shop attracts GST?",
    "Whether notification 4/2019 can be followed and GST be paid on RCM basis "
    "for the share of land?",
    "Whether transfer of development rights attracts GST",
    "GST on sale of land after levelling and laying of drainage lines",
])
def test_an_immovable_property_question_is_not_classification(brief):
    assert is_about_immovable_property(row(brief))
    assert not is_classification(row(brief))


def test_the_ruling_that_slipped_through_is_now_screened():
    """It carried 97(2)(a), which is why the clause test was not enough."""
    r = row("1. As to whether GST is payable on the transfer of leasehold "
            "rights in respect of the consideration of Rs. 15 Crores received "
            "by them for the land allotted by SIPCOT?",
            category="97(2)(a) & (g)")
    assert not is_about_services(r)      # the services screen never saw it
    assert is_about_immovable_property(r)
    assert not is_classification(r)


@pytest.mark.parametrize("brief", [
    "Clarification on classification of plastic Seedling Trays and applicable "
    "rate of tax",
    "Whether Tamarind Seed attracts Nil Rate of Tax under HSN Code 1209",
    "What is the rate of tax applicable for veterinary instruments known as AI crate",
    "Classification of goods and determination of tax liability of product "
    "under HSN 2919",
    "Whether the printed advertisement materials are classifiable as supply of goods?",
])
def test_goods_questions_are_untouched(brief):
    assert not is_about_immovable_property(row(brief))
    assert is_classification(row(brief))


def test_a_passing_mention_in_the_facts_does_not_disqualify():
    """The screen reads the brief only. Widening it to the facts drops a real
    goods ruling that mentions land once."""
    r = row("Whether the printed advertisement materials are classifiable as "
            "supply of goods?")
    assert is_classification(r)
    # Even with land-heavy facts, the question is still about goods.
    assert not is_about_immovable_property(r)


def test_goods_that_merely_sound_like_property_survive():
    for brief in ("Classification of prefabricated building panels",
                  "Rate of tax on doors, windows and frames of iron",
                  "Applicable rate for cement used in construction"):
        assert not is_about_immovable_property(row(brief))
