"""Looking a heading up in the archived Gazette.

This is a document lookup, and the tests below pin the one property that makes
it safe: it resolves a heading only when the notification leaves no choice, and
reports every competing entry when it does.
"""

import pytest

from harness.collect.schedule_lookup import RATED, SCHEDULE_SLAB, lookup

pytestmark = pytest.mark.skipif(
    not RATED.exists(), reason="archived notifications not present"
)


@pytest.fixture(autouse=True)
def _needs_pypdf():
    pytest.importorskip("pypdf")


# --- headings that resolve -------------------------------------------------


@pytest.mark.parametrize(
    "heading,slab",
    [
        ("2523", "18"),   # cement, Schedule II
        ("3923", "18"),   # plastic packing articles
        ("5603", "5"),    # nonwovens, Schedule I
        ("4911", "18"),   # other printed matter
        ("2501", "0"),    # salt, exempt
    ],
)
def test_unambiguous_headings_resolve(heading, slab):
    assert lookup(heading).slab == slab


def test_resolved_heading_reports_where_it_found_it():
    m = lookup("2523")
    assert m.schedule == "II"
    assert "Portland cement" in m.entries[0].text


# --- headings that must NOT resolve ---------------------------------------


@pytest.mark.parametrize(
    "heading,why",
    [
        ("9608", "pens and their parts at 18%, pencils exempt"),
        ("8711", "350 cc splits 18% from 40%"),
        ("7418", "household articles of copper 5%, all other 18%"),
        ("2202", "added sugar splits 5% from 40%"),
        ("1101", "pre-packaged and labelled splits 5% from exempt"),
        ("3306", "toothpaste 5%, other oral hygiene preparations 18%"),
    ],
)
def test_conditional_headings_stay_ambiguous(heading, why):
    m = lookup(heading)
    assert m.ambiguous, f"{heading} should not resolve: {why}"
    assert m.slab is None
    assert m.schedule is None


def test_ambiguous_lookup_reports_every_option():
    m = lookup("8711")
    slabs = {e.slab for e in m.entries}
    # Both sides of the 350 cc threshold must be visible to the annotator.
    assert {"18", "40"} <= slabs


def test_exempt_and_rated_entries_are_both_reported():
    m = lookup("1101")
    assert m.entries and m.exempt_entries
    assert "pre-packaged and labelled" in m.entries[0].text
    assert "other than pre-packaged" in m.exempt_entries[0]


# --- schedule table --------------------------------------------------------


def test_schedule_vii_has_no_current_slab():
    # Omitted by Notification 19/2025 from 1 Feb 2026.
    assert SCHEDULE_SLAB["VII"] is None


def test_no_abolished_slab_is_reachable():
    from harness.schema import ABOLISHED_SLABS

    assert not (set(filter(None, SCHEDULE_SLAB.values())) & ABOLISHED_SLABS)


def test_unknown_heading_returns_no_slab():
    m = lookup("0000")
    assert m is not None and m.slab is None
