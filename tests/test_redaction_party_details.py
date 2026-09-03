"""Party details that reached the corpus and had to be redacted after the fact.

Every case here is a real leak found by scanning the collected rulings, not a
hypothetical. The dataset is published, so a pattern that only *usually* works
is a pattern that publishes someone's tax identifier.

The strings below are synthetic reconstructions in the shape of the originals.
"""

from __future__ import annotations

import pytest

from harness.collect.normalise import normalise


def clean(text: str) -> str:
    return normalise(text, is_ruling=True)[0]


# --- identifiers ----------------------------------------------------------

def test_a_pan_is_stripped():
    out = clean("a firm incorporated on 11th June, 2012 having PAN-ABCDE1234F and "
                "registered office at Plot No.418, Kadodara.")
    assert "ABCDE1234F" not in out
    assert "PAN-" not in out


def test_a_bare_pan_shaped_token_is_stripped():
    assert "ABCDE1234F" not in clean("The applicant ABCDE1234F supplies bricks.")


def test_a_gstin_still_goes():
    assert "24ABCDE1234F1Z5" not in clean("GSTIN 24ABCDE1234F1Z5 of the applicant.")


@pytest.mark.parametrize("goods", [
    "pan masala preparations",
    "pan masala and gutkha",
    "The goods are pan preparations of chapter 21.",
])
def test_pan_the_keyword_does_not_eat_pan_the_goods(goods):
    """`pan masala` is a taxable good in this dataset. An earlier draft of the
    PAN pattern accepted any 8-12 character word after "pan" and removed it."""
    assert "pan" in clean(goods).lower()
    assert "masala" in clean(goods).lower() or "preparations" in clean(goods).lower()


# --- addresses ------------------------------------------------------------

def test_a_registered_office_without_a_street_word_is_stripped():
    """_STREET_ADDR_RE needs Road/Street/Nagar; "Plot No.418, Kadodara" has none."""
    out = clean("having registered office at Plot No.418, Kadodara, Navsari. "
                "The goods are ceramic tiles.")
    assert "Kadodara" not in out
    assert "ceramic tiles" in out          # the goods survive


def test_a_registered_office_in_prose_is_stripped():
    out = clean("The registered office is in Ramnagar, Telangana, India. "
                "They manufacture fly ash bricks.")
    assert "Ramnagar" not in out
    assert "fly ash bricks" in out


# --- company and personal names ------------------------------------------

@pytest.mark.parametrize("name", [
    "[redacted]",
    "M/s. Aster Air products Private",
    "[redacted]",
    "M/s. Coastal Blenders and Distillers Private",
    "[redacted]",          # no suffix — needs the general shape
])
def test_third_party_companies_are_stripped(name):
    out = clean(f"another player in a similar line, {name} appears to have "
                "been clearing the goods at 18%.")
    head = name.split()[1].rstrip(".,")
    assert head not in out


@pytest.mark.parametrize("text,stranded", [
    # "Private" is itself a suffix, so listing it before "Private Limited"
    # ends the lazy match early and leaves the rest behind.
    ("another player, M/s Acme Foods Private Limited, supplies atta", "Limited"),
    # A suffix word in the middle of a name does the same thing.
    ("supplier M/s Beta Traders Pvt Ltd. cleared the goods", "Pvt"),
    ("M/s Gamma Mills Private Limited manufactures flour", "Limited"),
])
def test_a_company_name_is_not_truncated_leaving_its_suffix(text, stranded):
    assert stranded not in clean(text)


def test_a_lowercase_word_inside_a_company_name_is_handled():
    """"[redacted]" — the capitalised-run pattern
    stops at "products", so the suffix pattern has to carry this one."""
    out = clean("from [redacted] they procure oxygen")
    assert "Aster" not in out and "Private" not in out
    assert "procure oxygen" in out


def test_an_individual_named_as_applicant_is_stripped():
    out = clean("Name and applicant M/s. Rajeshbhai Manilal Shah Milkat No. "
                "GSTIN of the applicant Date of application 06.01.2023")
    assert "Rajeshbhai" not in out and "Manilal" not in out


def test_the_goods_survive_a_company_strip():
    out = clean("[redacted] manufactures polypropylene tarpaulins "
                "of heading 6306.")
    assert "tarpaulins" in out and "6306" in out


# --- what must NOT be stripped -------------------------------------------

def test_a_government_order_citation_survives():
    """"M/?s" also matches the "Ms" in G.O.Ms. Without the (?!No) guard the
    company pattern deletes the statutory citation next to it."""
    out = clean("issued by Central Board of Excise and Customs and G.O.Ms No. 110, "
                "Revenue (CT -II) Department, Dt. 29-06-2017")
    assert "G.O.Ms No. 110" in out
    assert "Revenue" in out


def test_a_notification_ms_no_citation_survives():
    out = clean("as per Sl.No. 59 of Schedule I of Notification Ms. No. "
                "rr(2)/crR/s32(d-41/2017 vide G.O. (Ms) No. 62 dated 29.06.2017")
    assert "Notification Ms. No." in out
    assert "Schedule I" in out


def test_redaction_converges_in_one_pass():
    """Applying it twice must not keep eating text — otherwise the corpus
    depends on how many times it happened to be run."""
    text = ("[redacted], having PAN-ABCDE1234F and registered office "
            "at Plot No.12, Rajkot, manufactures fly ash bricks of heading 6815.")
    once = clean(text)
    assert clean(once) == once
