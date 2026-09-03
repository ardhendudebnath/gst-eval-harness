"""Redaction of personal names and addresses, and screening of withdrawn rulings.

Every case here reproduces the shape of something that actually reached the
pool during collection. Names and addresses are synthetic; the surrounding
phrasing, including the OCR damage, is faithful.
"""

import pytest

from harness.collect.aar import is_withdrawn
from harness.collect.normalise import normalise


def clean(text: str) -> tuple[str, list[str]]:
    return normalise(text, is_ruling=True)


# --- personal names -------------------------------------------------------


def test_representative_with_honorific_is_stripped():
    text = (
        "attract a levy of 12%? 3. Sri. Examplename, Advocate, the authorized "
        "representative of the Applicant appeared on behalf of the Applicant."
    )
    out, applied = clean(text)
    assert "Examplename" not in out
    assert "strip_person_name" in applied


def test_signature_block_member_name_is_stripped():
    text = "relevant technical details of the supply for Member, TNGST / Ms. Examplename Kata, IRS Member, CGST"
    out, _ = clean(text)
    assert "Examplename" not in out


def test_sole_proprietor_named_as_an_individual_is_stripped():
    # Proprietorship applicants are natural persons, not companies.
    text = (
        "under the Tamil Nadu Goods and Service Tax Act. Mr. Examplename Secondname, "
        "Prop. of Examplename doing business at 4th Cross, Sampletown."
    )
    out, applied = clean(text)
    assert "Examplename" not in out
    assert "strip_person_name" in applied


def test_applicant_street_address_is_stripped():
    text = "Mr. Examplename Rahman (Prop. : ), No. 18-100, Sample Main Road, Sampletown - 629702 (herein after referred as Applicant)"
    out, _ = clean(text)
    assert "Sample Main Road" not in out
    assert "629702" not in out


def test_doing_business_at_clause_is_stripped():
    out, applied = clean("The proprietor doing business at 12 Sample Street, Chennai. Goods follow.")
    assert "Sample Street" not in out
    assert "strip_business_address" in applied


# --- the false positive that must survive ---------------------------------


def test_government_order_citation_is_not_treated_as_a_name():
    # "G.O.Ms No. 110" is a Telangana Government Order reference. A bare
    # honorific pattern eats it and destroys legitimate legal citation.
    text = (
        "issued by Central Board of Excise and Customs and G.O.Ms No. 110, "
        "Revenue (CT-II) Department, Dt. 29-06-2017, issued by Government of Telangana."
    )
    out, applied = clean(text)
    assert "G.O.Ms No. 110" in out
    assert "Revenue (CT-II) Department" in out
    assert "strip_person_name" not in applied


def test_goods_text_survives_name_redaction():
    text = (
        "Sri. Examplename, Advocate appeared. The applicant manufactures PVC Carpet "
        "Mats classifiable under Tariff item 5705 00 49."
    )
    out, _ = clean(text)
    assert "PVC Carpet Mats" in out
    assert "5705 00 49" in out


# --- withdrawn applications -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The applicant appeared in person and requested to withdraw the application "
        "quoting the reason that there was an inadvertent mistake in their application",
        "the applicant was permitted to withdraw the application",
        "The application is withdrawn by the applicant",
        "the application is not maintainable",
        "rejected as inadmissible under section 98(2)",
    ],
)
def test_withdrawn_applications_are_detected(text):
    assert is_withdrawn(text)


@pytest.mark.parametrize(
    "text",
    [
        "The applicant manufactures Quartz Slabs from crushed quartz and resin.",
        "The applicant sought a ruling on the classification of PVC mats.",
        # "withdrawal" of goods from a warehouse is not a withdrawn application.
        "goods are cleared on withdrawal from the bonded store",
    ],
)
def test_live_rulings_are_not_flagged_as_withdrawn(text):
    assert not is_withdrawn(text)
