"""Abolished rates cited in the reasoning, not just given as the answer.

Every "should count" string below is a real response from the first run against
the endpoint, where three of four refusals reached UNANSWERABLE by way of a
dead rate and scored as clean abstentions.
"""

from __future__ import annotations

import pytest

from harness.prompt import Parsed
from harness.scorers.exact import find_abolished_citations, score_row, summarise
from harness.schema import Example


def gold(slab="18", hsn4="6815"):
    return Example(id="gst-0001", input="fly ash bricks", slab=slab, hsn4=hsn4,
                   answerable=slab != "UNANSWERABLE", justification="x",
                   difficulty="typical")


def parsed(slab, *, hsn4="6815", answerable=True, unparseable=False):
    return Parsed(slab=slab, hsn4=hsn4, answerable=answerable,
                  justification="", unparseable=unparseable)


# --- what must be caught --------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("The goods comprise slide fasteners (12% GST) and parts/sliders (18% GST), "
     "so no unique rate can be assigned.", ["12"]),
    ("two distinct products with different GST rates (5% for bricks, 12% for "
     "blocks), so a single rate cannot be determined.", ["12"]),
    ("Heading 4911 is taxed at 12% under the GST rate schedule.", ["12"]),
    ("the GST schedule entry for 2523 fixes the rate at 28% GST", ["28"]),
    ("attracts 12 per cent", ["12"]),
    ("chargeable @ 28 %", ["28"]),
    ("either 12% or 28% depending on the variant", ["12", "28"]),
])
def test_an_abolished_rate_asserted_as_current_is_found(text, expected):
    assert find_abolished_citations(text) == expected


# --- what must not be ----------------------------------------------------

@pytest.mark.parametrize("text", [
    "The rate was 12% until 22 September 2025 and is now 18%.",
    "12% has been abolished; the current rate is 18%.",
    "Prior to Notification 9/2025 these goods attracted 28%.",
    "The 28% slab was omitted with effect from 1 February 2026.",
    "Previously 12%, now taxed under Schedule II.",
    "The erstwhile 28% rate no longer applies.",
])
def test_correct_gst_history_is_not_counted_as_staleness(text):
    """Knowing a rate died is the opposite of reciting it."""
    assert find_abolished_citations(text) == []


@pytest.mark.parametrize("text", [
    "SLAB: 18\nHSN: 2523",
    "The consignment weighed 12 kg and measured 28 mm.",
    "Heading 2801 covers this; serial 128 of Schedule II applies.",
    "Rule 12 of the CGST Rules and section 28 are not relevant.",
    "",
])
def test_numbers_that_are_not_rates_are_left_alone(text):
    assert find_abolished_citations(text) == []


# --- the metric ----------------------------------------------------------

def test_a_refusal_reasoned_from_a_dead_rate_is_now_visible():
    """The exact case the old metric missed: scored as an abstention, with
    nothing recording that the model got there through an abolished slab."""
    s = score_row(gold(), parsed("UNANSWERABLE", answerable=False),
                  text="SLAB: UNANSWERABLE\nWHY: two products with different "
                       "rates (5% for bricks, 12% for blocks).")
    assert s.stale_slab is None          # the answer named no dead rate
    assert s.stale_cited == ("12",)      # the reasoning did
    assert s.recites_dead_schedule


def test_answering_with_a_dead_rate_still_counts_both_ways():
    s = score_row(gold(), parsed("28", hsn4="2523"),
                  text="SLAB: 28\nWHY: 2523 is taxed at 28%.")
    assert s.stale_slab == "28" and s.stale_cited == ("28",)


def test_a_clean_answer_records_nothing():
    s = score_row(gold(), parsed("18"),
                  text="SLAB: 18\nWHY: Schedule II covers it.")
    assert not s.recites_dead_schedule


def test_an_unparseable_response_can_still_recite_a_dead_rate():
    s = score_row(gold(), parsed(None, hsn4=None, answerable=None, unparseable=True),
                  text="I'd say roughly 28% for cement.")
    assert s.unparseable and s.stale_cited == ("28",)


def test_the_summary_separates_the_two_rates():
    rows = [
        score_row(gold(), parsed("18"), text="SLAB: 18"),
        score_row(gold(), parsed("12"), text="SLAB: 12\nWHY: taxed at 12%."),
        score_row(gold(), parsed("UNANSWERABLE", answerable=False),
                  text="WHY: 5% for bricks, 12% for blocks, so unclear."),
        score_row(gold(), parsed("5"), text="SLAB: 5\nWHY: Schedule I."),
    ]
    s = summarise(rows)

    assert s.n == 4
    assert s.stale_slab_rate == 0.25         # one answered 12%
    assert s.stale_cited_rate == 0.5         # that one, plus the refusal
    assert s.stale_cited_by_slab == {"12": 2}
    row = s.as_row()
    assert row["stale_cited_rate"] == 0.5


def test_the_cited_rate_is_never_below_the_answered_rate():
    rows = [score_row(gold(), parsed("28", hsn4="2523"), text="SLAB: 28")]
    s = summarise(rows)
    assert s.stale_cited_rate >= s.stale_slab_rate


def test_scoring_without_the_text_still_works():
    """Callers that never pass a response must keep their old behaviour."""
    s = score_row(gold(), parsed("18"))
    assert s.slab_correct and s.stale_cited == ()
