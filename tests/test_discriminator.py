"""What separates two competing schedule entries, in the Gazette's own words.

These schedules are built the same way throughout: one entry enumerates
particular goods at a lower rate, another sweeps up the rest and excludes them
by name. The exclusion clause states the axis, so surfacing it turns an
annotator's job from "read two extracts and work out what separates them" into
"is this good one of these?".

Every string is real notification text.
"""

from __future__ import annotations

import pytest

from harness.collect.schedule_lookup import (
    RATED,
    Entry,
    Match,
    _entry_text,
    _tidy_clause,
    lookup,
)

pytestmark = pytest.mark.skipif(
    not RATED.exists(), reason="archived notification not present"
)


def match_of(*texts: str) -> Match:
    """Entries at *different* rates, because `decides_it` only speaks when the
    heading is genuinely ambiguous — two entries at the same rate leave the
    annotator nothing to decide."""
    rates = [("I", "5"), ("II", "18"), ("III", "40")]
    return Match(heading="0000",
                 entries=[Entry(*rates[i % 3], t) for i, t in enumerate(texts)])


# --- the clause ----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("8708 Parts and accessories of the motor vehicles of headings 8701 to "
     "8705 [other than specified parts of tractors]", "specified parts of tractors"),
    ("8504 Electrical transformers, static converters and inductors other than "
     "charger or charging station for Electrically operated vehicles",
     "charger or charging station for Electrically operated vehicles"),
    ("3926 Other articles of plastics [other than bangles of plastic, plastic "
     "beads and feeding bottles]",
     "bangles of plastic, plastic beads and feeding bottles"),
    ("2401 Tobacco, other than tobacco leaves", "tobacco leaves"),
])
def test_the_exclusion_clause_is_the_axis(text, expected):
    assert match_of(text, "second entry so it is ambiguous").decides_it == expected


def test_a_closing_paren_ends_the_clause():
    """"(other than medicaments) including sunscreen ..." excludes medicaments.
    Running past the paren swept the whole following list into the clause."""
    m = match_of("3304 Beauty preparations (other than medicaments) including "
                 "sunscreen or sun tan preparations; kajal, kumkum, bindi",
                 "second entry")
    assert m.decides_it == "medicaments"


def test_an_unambiguous_heading_has_no_axis_to_state():
    assert Match(heading="2523", entries=[Entry("II", "18", "x")]).decides_it is None


def test_a_heading_with_no_exclusion_returns_none():
    m = match_of("1905 Pastry, cakes, biscuits", "1905 Pappad, by whatever name")
    assert m.decides_it is None


def test_several_clauses_are_joined_but_capped():
    long = " ".join(f"other than thing{i} of some considerable length here"
                    for i in range(6))
    m = match_of(long, "second entry")
    got = m.decides_it
    assert got and len(got) <= 202


# --- entry text ----------------------------------------------------------

def test_an_entry_stops_where_the_next_serial_begins():
    """A fixed window ran into the following entries, so heading 3307's
    extract arrived carrying serials 250 and 251 — agarbatti and toilet soap,
    which are different headings entirely."""
    text = ("249. 3307 Shaving cream, shaving lotion, aftershave lotion "
            "250. 3307 41 00 Agarbatti, lobhan, dhoop batti "
            "251. 3401 Toilet Soap")
    got = _entry_text(text, text.index("3307"))
    assert "Shaving cream" in got
    assert "Agarbatti" not in got and "Toilet Soap" not in got


def test_a_truncated_clause_says_so():
    assert _tidy_clause("shaving cream, shavin", truncated=True).endswith("…")


def test_a_complete_clause_keeps_its_last_word():
    """Dropping the last word to handle a half-word cost a whole word from
    every clause that merely ended where its entry ended: "rice bran" became
    "rice"."""
    assert _tidy_clause("rice bran", truncated=False) == "rice bran"
    assert _tidy_clause("pre-packaged and labelled", truncated=False) == \
        "pre-packaged and labelled"


def test_a_trailing_serial_number_is_stripped():
    assert _tidy_clause("not to be used as fertilizers 24", truncated=False) == \
        "not to be used as fertilizers"


# --- against the real notification ---------------------------------------

@pytest.mark.parametrize("heading,fragment", [
    ("8708", "tractors"),
    ("8504", "charging station"),
    ("3926", "feeding bottles"),
    ("2401", "tobacco leaves"),
    ("9608", "9609"),
])
def test_real_headings_state_their_axis(heading, fragment):
    got = lookup(heading).decides_it
    assert got and fragment.lower() in got.lower()


def test_a_resolved_heading_states_no_axis():
    assert lookup("2523").decides_it is None      # unambiguous, 18 %
