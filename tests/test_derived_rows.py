"""Gazette-derived rows: admissible, but never passing as human judgement.

The dataset's central claim is what `labelled_by` says. These pin the boundary
from both sides — a derived row is valid in the golden set, and it is not a
human label, and neither fact may quietly become the other.
"""

from __future__ import annotations

from datetime import date

import pytest

from harness.label.derive import LONG_CONTEXT_WORDS, difficulty_for
from harness.schema import (
    DERIVED_LABELLERS,
    LABELLERS,
    QUARANTINED_LABELLERS,
    Example,
    validate_example,
)


def row(labelled_by="gazette-derived", **kw):
    base = dict(id="gst-0001", input="fly ash bricks", slab="18", hsn4="6815",
                answerable=True, justification="Sch II", difficulty="typical",
                labelled_by=labelled_by, labelled_at=str(date.today()))
    base.update(kw)
    return Example(**base)


def test_a_derived_row_is_valid_in_the_golden_set():
    assert validate_example(row()) == []


def test_a_derived_row_is_not_quarantined():
    """It is admissible — that is the point of the separate value."""
    assert "gazette-derived" not in QUARANTINED_LABELLERS
    assert "gazette-derived" in LABELLERS


def test_a_derived_row_is_not_a_human_label():
    """The distinction the README's provenance table rests on."""
    assert DERIVED_LABELLERS.isdisjoint({"human", "human-reviewed"})
    assert row().labelled_by not in {"human", "human-reviewed"}


def test_an_unreviewed_model_row_is_still_rejected():
    """Adding a new admissible value must not have widened the gate."""
    problems = validate_example(row(labelled_by="model-first-pass"))
    assert problems and "model-first-pass" in problems[0]


def test_an_unknown_labeller_is_still_rejected():
    problems = validate_example(row(labelled_by="gazette_derived"))
    assert problems


def test_a_derived_row_still_cannot_carry_an_abolished_slab():
    problems = validate_example(row(slab="28"))
    assert problems and "abolished" in problems[0]


# --- difficulty ----------------------------------------------------------

def test_long_inputs_are_long_context():
    assert difficulty_for("word " * LONG_CONTEXT_WORDS) == "long_context"


def test_short_inputs_are_typical():
    assert difficulty_for("fly ash bricks, 230 mm") == "typical"


@pytest.mark.parametrize("n", [LONG_CONTEXT_WORDS - 1, LONG_CONTEXT_WORDS])
def test_the_boundary_is_where_it_says_it_is(n):
    expected = "long_context" if n >= LONG_CONTEXT_WORDS else "typical"
    assert difficulty_for("word " * n) == expected


def test_derivation_never_assigns_a_judgement_stratum():
    """`hard` and `adversarial` are calls a lookup cannot make. If this ever
    starts producing them, the module has begun judging."""
    for n in (1, 50, 799, 800, 5000):
        assert difficulty_for("word " * n) in {"typical", "long_context"}
