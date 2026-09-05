"""Redaction must not eat the goods.

No test asserted this, which is how a pattern that deleted "MS Rod, MS Flat and
MS Bracket" reached the published dataset and got scored. The goods description
is the entire content of an example; a redactor that removes it has destroyed
the row more thoroughly than a leak would have.

Every string here is real corpus text.
"""

from __future__ import annotations

import pytest

from harness.collect.normalise import normalise


def clean(text: str) -> str:
    return normalise(text, is_ruling=True)[0]


@pytest.mark.parametrize("goods", [
    # MS is mild steel, and it is all over a tariff corpus.
    "The applicant manufactures MS Rod, MS Flat and MS Bracket of heading 7214",
    "supply of MS Dummy Coin and MS Square rod to the customer",
    "MS Pipes and GI Pipes classifiable under 7306",
    "fabrication using MS Angle, MS Channel and MS Plate",
    # Other two-letter prefixes that look like abbreviations.
    "PP Woven Sacks of heading 6305",
    "HDPE and LDPE granules under chapter 39",
    "CI castings and SS Sheets supplied to the buyer",
])
def test_goods_descriptions_survive_intact(goods):
    assert clean(goods) == goods


@pytest.mark.parametrize("phrase,keep", [
    ("MS State Government tender for mild steel items", "mild steel"),
    # "MS Excel", not "Ms Excel" — the honorific pattern is case-sensitive on
    # purpose, and the capitalised form is what documents actually contain.
    ("MS Excel sheets were annexed to the application", "Excel"),
    ("the goods are pan masala preparations", "pan masala"),
    ("clear glass bottles of 750 ml", "glass bottles"),
    ("cat food, 400 g pouch, chapter 23", "cat food"),
    ("make up kit of heading 3304", "make up kit"),
])
def test_ordinary_words_that_look_like_markers_survive(phrase, keep):
    assert keep in clean(phrase)


def test_a_party_beside_goods_goes_but_the_goods_stay():
    out = clean("M/s. Kesari Industries manufactures MS Rod and MS Flat "
                "falling under heading 7214")
    assert "Kesari" not in out
    assert "MS Rod" in out and "MS Flat" in out and "7214" in out


def test_redaction_never_removes_most_of_a_line():
    """A blunt guard against the whole class. If a pattern ever takes more than
    half of an ordinary goods sentence, something is badly wrong."""
    sentences = [
        "The applicant manufactures MS Rod, MS Flat and MS Bracket of heading 7214",
        "supply of MS Dummy Coin and MS Square rod to the customer",
        "polypropylene tarpaulins of heading 6306 sold by the piece",
        "fly ash bricks containing 60 percent fly ash by weight",
    ]
    for s in sentences:
        out = clean(s)
        assert len(out) >= len(s) * 0.5, f"redaction removed most of: {s!r} -> {out!r}"
