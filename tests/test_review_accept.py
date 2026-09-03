"""Accepting a grounded suggestion during review.

Accepting is a human decision made with the Gazette entry in front of you, and
the row it produces is marked human-reviewed. What the model may not decide for
you is pinned here: difficulty is always asked, and the rate-changed tag is
confirmed rather than assumed.
"""

import pytest

from harness.label.cli import _accept
from harness.schema import UNCERTAIN, Example, validate_example


def suggestion(**over) -> Example:
    base = dict(
        id="gst-0001",
        input="The applicant manufactures Portland cement in 50 kg bags.",
        slab="18",
        hsn4="2523",
        answerable=True,
        justification="Heading 2523 per the operative ruling; 18% per Schedule II.",
        difficulty="hard",
        tags=["rate-changed-2025"],
        source="aar",
        source_id="x.pdf",
        labelled_by="model-first-pass",
        model_notes={"rate_moved": True, "rate_moved_basis": "authority held 12%"},
    )
    base.update(over)
    return Example(**base)


def answers(monkeypatch, *responses):
    it = iter(responses)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(it))


def test_accept_keeps_the_grounded_slab_and_heading(monkeypatch):
    answers(monkeypatch, "2", "n")  # difficulty=hard, no rate-changed tag
    ex = _accept(suggestion(), {"rate_moved": False})
    assert ex.slab == "18" and ex.hsn4 == "2523"
    assert "Schedule II" in ex.justification


def test_difficulty_is_always_asked(monkeypatch):
    # The model has no basis for it — it is a judgement about the dataset,
    # not about the goods.
    answers(monkeypatch, "4")
    ex = _accept(suggestion(difficulty="hard"), {})
    assert ex.difficulty == "adversarial"


def test_rate_changed_tag_is_confirmed_not_assumed(monkeypatch):
    # The model infers it from the ruling's stated rate, which in one real
    # case was the applicant's rejected argument rather than the holding.
    answers(monkeypatch, "2", "n")
    ex = _accept(suggestion(), {"rate_moved": True, "rate_moved_basis": "b"})
    assert "rate-changed-2025" not in ex.tags


def test_rate_changed_tag_applied_when_confirmed(monkeypatch):
    answers(monkeypatch, "2", "y")
    ex = _accept(suggestion(), {"rate_moved": True, "rate_moved_basis": "b"})
    assert "rate-changed-2025" in ex.tags


def test_not_asked_when_the_model_did_not_claim_a_move(monkeypatch):
    answers(monkeypatch, "1")  # only difficulty consumed
    ex = _accept(suggestion(tags=[]), {"rate_moved": False})
    assert "rate-changed-2025" not in ex.tags


def test_accepted_row_validates_for_the_golden_set(monkeypatch):
    answers(monkeypatch, "2", "n")
    ex = _accept(suggestion(), {})
    ex.labelled_by = "human-reviewed"
    assert validate_example(ex) == []


def test_provenance_is_recorded_in_the_notes(monkeypatch):
    answers(monkeypatch, "2", "n")
    assert "accepted model first pass" in _accept(suggestion(), {}).labeller_notes


def test_uncertain_suggestions_are_never_acceptable():
    # Only a Gazette-grounded slab is offered for one-key acceptance; an
    # UNCERTAIN row has nothing to accept and must go through full labelling.
    assert suggestion(slab=UNCERTAIN).slab == UNCERTAIN
    ex = suggestion(slab=UNCERTAIN)
    ex.labelled_by = "human"
    assert any(UNCERTAIN in p for p in validate_example(ex))
