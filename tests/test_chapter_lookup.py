"""Chapter-level entries in the rate schedules.

The notifications specify a great deal of the tariff at chapter level rather
than heading level — "63 [other than 6305 32 00, 6305 33 00, 6309] Other made
up textile articles" — so a heading with no entry of its own is usually covered
rather than unlisted. Reporting "not found" for those was wrong in the
direction that matters: it reads as the notification being silent when it is
not.

These run against the real archived Gazette, so they also guard the extraction.
"""

from __future__ import annotations

import pytest

from harness.collect.schedule_lookup import RATED, lookup

pytestmark = pytest.mark.skipif(
    not RATED.exists(), reason="archived notifications not present"
)


def test_a_heading_with_its_own_entry_is_unaffected():
    """The fallback must never invent competition for a listed heading."""
    m = lookup("6810")
    assert m.entries and not m.chapter_entries
    assert m.slab == "18"
    assert not m.chapter_only


@pytest.mark.parametrize("heading,slab", [
    ("3004", "5"), ("3923", "18"), ("5903", "5"), ("6815", "18"), ("8501", "18"),
])
def test_headings_that_already_resolved_still_do(heading, slab):
    m = lookup(heading)
    assert m.slab == slab
    assert not m.chapter_entries


def test_a_heading_absent_from_the_schedules_finds_its_chapter():
    """6306 (tarpaulins, tents, sails) has no heading-level entry."""
    m = lookup("6306")
    assert not m.entries
    assert m.chapter_only
    assert {e.schedule for e in m.chapter_entries} == {"I", "II"}
    assert {e.slab for e in m.chapter_entries} == {"5", "18"}


def test_a_chapter_entry_never_resolves_a_slab():
    """It is a pointer, not a determination: chapter entries carry exclusions,
    and reading whether goods sit inside one is the annotator's judgement."""
    m = lookup("6306")
    assert m.slab is None
    assert m.ambiguous  # two rates for the chapter is a real choice


def test_the_quoted_entry_shows_the_split_the_annotator_must_read():
    m = lookup("6306")
    text = " ".join(e.text for e in m.chapter_entries)
    assert "2500" in text  # chapter 63 splits on sale value per piece
    assert "textile" in text.lower()


def test_2919_falls_back_to_a_single_chapter_entry():
    """Chapter 29 is specified once: 'All organic chemicals other than
    giberellic acid', Schedule II."""
    m = lookup("2919")
    assert not m.entries and m.chapter_only
    assert [e.schedule for e in m.chapter_entries] == ["II"]
    assert "organic chemicals" in m.chapter_entries[0].text.lower()


def test_even_a_single_chapter_entry_does_not_resolve_the_slab():
    """That entry carries an exclusion. Confirming these goods are not the
    excluded ones is a reading, and the annotator does it."""
    m = lookup("2919")
    assert m.slab is None
    assert "other than" in m.chapter_entries[0].text.lower()


def test_a_two_digit_fragment_of_a_tariff_code_is_not_a_chapter():
    """Regression: the '29' inside '0101 29 Live horses' matched as chapter 29
    and offered live horses as an organic chemical. Every genuine chapter entry
    is introduced by its serial number, which is what distinguishes them."""
    m = lookup("2919")
    joined = " ".join(e.text for e in m.chapter_entries).lower()
    assert "live horses" not in joined
    assert not any(e.schedule == "I" for e in m.chapter_entries)


def test_returned_entries_are_prose_not_numbering():
    m = lookup("6306")
    for e in m.chapter_entries:
        assert len(e.text) > 40
        assert any(c.isalpha() for c in e.text)


def test_ambiguity_is_still_refused_for_a_genuinely_split_heading():
    """2202 splits on added sugar; the fallback must not have papered over it."""
    m = lookup("2202")
    assert m.ambiguous and m.slab is None
    assert not m.chapter_entries  # it has its own entries
