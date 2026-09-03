"""Telling the authority's holding apart from the applicant's argument.

The pen-tips ruling is the worked case: the applicant argued the goods were
taxable at 12%, and the authority placed them in Schedule III of Notification
1/2017, which was 18%. Scanning the document for "12%" finds the argument and
calls it the rate — wrong on 8 of 29 rulings before this existed.
"""

import pytest

from harness.collect.ruling_outcome import OLD_SCHEDULE_RATES, extract_outcome
from harness.label.first_pass import suggest
from tests.test_ruling_outcome import PREAMBLE, SIGN_OFF


def ruling(body: str) -> str:
    return PREAMBLE + " R U L I N G " + body + SIGN_OFF


def test_schedule_iii_is_eighteen_not_twelve():
    # The real pen-tips holding.
    out = extract_outcome(
        ruling(
            "“Tips and Balls” of Ball Point Pens are to be classified under GST "
            "Tariff Heading 9608 99 90 and included under Sl No. 453 of Schedule "
            "III of Notification No. 01/2017-Central Tax (Rate)."
        )
    )
    assert out.schedule == "III"
    assert out.held_rate == "18"


@pytest.mark.parametrize(
    "roman,rate", [("I", "5"), ("II", "12"), ("III", "18"), ("IV", "28"), ("V", "3")]
)
def test_every_old_schedule_maps_to_its_rate(roman, rate):
    out = extract_outcome(
        ruling(f"The goods are classifiable under Heading 1234 of Schedule {roman}.")
    )
    assert out.held_rate == rate
    assert OLD_SCHEDULE_RATES[roman] == rate


def test_split_cgst_rate_is_the_holding_when_no_schedule():
    out = extract_outcome(
        ruling(
            "The goods are classifiable under chapter heading 4911 and the rate "
            "of tax applicable is 6% CGST + 6% SGST."
        )
    )
    assert out.held_rate == "12"


def test_no_schedule_and_no_rate_leaves_the_holding_unknown():
    out = extract_outcome(
        ruling("The goods are classifiable under Tariff Heading 8413 91 90.")
    )
    assert out.held_rate is None


# --- what the first pass concludes from it --------------------------------


def _record(**over) -> dict:
    base = {
        "source": "aar",
        "source_id": "no-such-file.pdf",
        "input": "The applicant manufactures widgets of assorted kinds and sizes.",
        "collection_meta": {"stale_rates_in_ruling": ["12", "18"]},
    }
    base.update(over)
    return base


def test_no_tag_when_the_holding_is_unknown():
    # The cached PDF is absent, so nothing can be established — and a document
    # full of "12%" must not be enough on its own.
    ex = suggest(_record(), "gst-0001")
    assert "rate-changed-2025" not in ex.tags
    assert ex.model_notes["rate_moved"] is False
    assert "unknown" in ex.model_notes["rate_moved_basis"]


def test_basis_is_recorded_even_when_undetermined():
    notes = suggest(_record(), "gst-0001").model_notes
    assert "authority_held_rate" in notes
    assert "authority_schedule" in notes
