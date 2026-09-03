"""Quarantine guarantees for the model first pass.

The plan permits model assistance only with full human review and explicit
disclosure. These tests are the mechanical half of that promise: an unreviewed
model suggestion must be incapable of becoming a dataset example, including by
someone simply concatenating the files.
"""

from pathlib import Path

import pytest

from harness.label.first_pass import GOLDEN, QUARANTINE, suggest
from harness.schema import UNANSWERABLE, UNCERTAIN, Example, validate_example

RECORD = {
    "source": "aar",
    "source_id": "no-such-file.pdf",
    "input": "The Applicant manufactures ball point pen tips and balls of assorted sizes "
    "for use in the manufacture of pens, and supplies them to dealers.",
    "collected_at": "2026-09-03T12:00:00+00:00",
    "collection_meta": {
        "state": "West Bengal",
        "order_no": "44/WBAAR/2018-19",
        "stale_rates_in_ruling": ["12", "18"],
        "hsn_candidates": ["9608"],
    },
}


def _suggestion() -> Example:
    return suggest(RECORD, "gst-0001")


# --- the quarantine guarantee ---------------------------------------------


def test_suggestion_is_marked_as_model_authored():
    assert _suggestion().labelled_by == "model-first-pass"


def test_suggestion_is_rejected_from_the_golden_set():
    problems = validate_example(_suggestion())
    assert any("unreviewed model suggestion" in p for p in problems)


def test_suggestion_is_valid_in_the_quarantine_file():
    assert validate_example(_suggestion(), quarantine=True) == []


def test_uncertain_slab_is_rejected_from_the_golden_set():
    ex = _suggestion()
    ex.labelled_by = "human"  # even relabelled, the sentinel cannot pass
    assert any(UNCERTAIN in p and "never in the golden set" in p
               for p in validate_example(ex))


def test_quarantine_is_not_the_golden_file():
    assert QUARANTINE != GOLDEN
    assert QUARANTINE == Path("data/first_pass.jsonl")


def test_reviewed_row_is_accepted():
    ex = _suggestion()
    ex.labelled_by = "human-reviewed"
    ex.slab = "5"
    ex.hsn4 = "9608"
    ex.justification = "Pen parts, HSN 9608, Notification 9/2025 Schedule I."
    ex.model_notes = {}
    assert validate_example(ex) == []


# --- what the first pass will and will not assert -------------------------


def test_no_slab_is_ever_proposed():
    # Deriving one needs Notification 9/2025, and rate_schedule.md is not yet
    # verified. A guess would anchor the reviewer on exactly the examples where
    # model priors are least trustworthy.
    assert _suggestion().slab == UNCERTAIN


def test_uncertain_is_not_unanswerable():
    # UNANSWERABLE is a positive finding about the description; UNCERTAIN is an
    # admission about the model. Conflating them would let model ignorance
    # masquerade as a dataset label.
    assert UNCERTAIN != UNANSWERABLE
    assert _suggestion().slab != UNANSWERABLE


def test_document_mentions_of_twelve_percent_do_not_set_the_tag():
    # This record's stale_rates_in_ruling contains "12", but that scan cannot
    # tell the authority's holding from the applicant's rejected argument. In
    # the real pen-tips ruling the applicant argued 12% and the authority
    # placed the goods in Schedule III, which was 18%.
    ex = _suggestion()
    assert "12" in ex.collection_meta["stale_rates_in_ruling"]
    assert "rate-changed-2025" not in ex.tags
    assert ex.model_notes["rate_moved"] is False


def test_no_rate_changed_tag_without_an_abolished_source_slab():
    record = {**RECORD, "collection_meta": {**RECORD["collection_meta"],
                                            "stale_rates_in_ruling": ["18"]}}
    ex = suggest(record, "gst-0002")
    assert "rate-changed-2025" not in ex.tags


def test_missing_pdf_yields_no_heading_and_says_so():
    ex = _suggestion()  # cached PDF deliberately absent
    assert ex.hsn4 is None
    assert ex.model_notes["hsn_confidence"] == "none"


def test_model_is_recorded_for_disclosure():
    assert _suggestion().model_notes["model"] == "claude-opus-5"


def test_notes_state_the_row_needs_review():
    assert "review" in _suggestion().labeller_notes.lower()


@pytest.mark.parametrize("field", ["slab_confidence", "slab_basis", "hsn_basis"])
def test_every_suggestion_carries_its_basis(field):
    assert field in _suggestion().model_notes
