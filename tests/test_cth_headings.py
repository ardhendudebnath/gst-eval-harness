"""CTH — Customs Tariff Heading — as a heading prefix.

Advance rulings write it constantly: "classifiable under CTH 73151100". The
extractor's prefix list did not include it, so those determinations yielded no
heading at all and the rulings sat outside the grounded pool. Seven of the 63
headingless rulings state their heading this way and no other.

Every string here is real corpus text, shortened.
"""

from __future__ import annotations

import pytest

from harness.collect.ruling_outcome import _HSN


def heads(text: str) -> list[str]:
    return [h.replace(" ", "") for h in _HSN.findall(text)]


@pytest.mark.parametrize("text,expected", [
    ("are classifiable under CTH 73151100 of the First Schedule", ["73151100"]),
    ("'Inverted tooth chains' under CTH 73151290", ["73151290"]),
    ("The classification of the products is CTH 2706", ["2706"]),
    ("more specifically under CTH 8708 8000", ["87088000"]),
    ("is classifiable under CTH 46019900", ["46019900"]),
    ("being a convertor is classifiable under CTH 8504", ["8504"]),
    ("falls under C.T.H. 8504 4090", ["85044090"]),
    ("under C T H 2401 2090", ["24012090"]),
    ("under Customs Tariff Heading 2706", ["2706"]),
])
def test_cth_forms_yield_the_heading(text, expected):
    assert heads(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("classifiable under HSN 6810", ["6810"]),
    ("under heading 3923", ["3923"]),
    ("under tariff item 1518 00 00", ["15180000"]),
    ("chapter heading 8413", ["8413"]),
    ("sub-heading 5603 94", ["560394"]),
])
def test_the_existing_prefixes_still_work(text, expected):
    assert heads(text) == expected


@pytest.mark.parametrize("text", [
    "under Notification No. 01/2017-Central Tax (Rate) dated 28.06.2017",
    "as per Notification 9/2025 dated 17.09.2025",
    "under Section 98 of the Central Goods and Services Tax Act, 2017",
    "vide order dated 30.07.2021 of this Authority",
])
def test_a_notification_or_a_year_is_not_a_heading(text):
    """The prefix requirement is what prevents this. A bare "classifiable
    under <digits>" was considered and rejected: the pattern allows 25
    non-digit characters before the number, so "classifiable under
    Notification No. 01/2017" would capture 2017 as a tariff heading."""
    assert heads(text) == []


def test_cth_does_not_match_ordinary_words_starting_with_c():
    for text in ("the catch 2202 was", "such 6810 articles", "CTH without a number"):
        assert all(len(h) >= 4 for h in heads(text))


def test_a_conditional_determination_keeps_both_headings():
    """"Heading 3307 or 3401" — a ruling that names two competing headings is
    exactly the case the annotator needs to see in full."""
    from harness.collect.ruling_outcome import _HSN_ALT
    text = "classifiable under CTH 3307 or 3401 depending on constituents"
    assert heads(text) == ["3307"]
    assert [h.replace(" ", "") for h in _HSN_ALT.findall(text)] == ["3401"]
