import pytest

from harness.schema import UNANSWERABLE, Example, next_id, validate_example


def make(**over) -> Example:
    base = dict(
        id="gst-0001",
        input="Aashirvaad Whole Wheat Atta, 5 kg, pack",
        slab="5",
        hsn4="1101",
        answerable=True,
        justification="Wheat flour, HSN 1101, pre-packaged and labelled, Schedule I.",
        difficulty="hard",
        tags=["conditionality"],
        source="off",
    )
    base.update(over)
    return Example(**base)


def test_valid_example_has_no_problems():
    assert validate_example(make()) == []


def test_abolished_slab_is_rejected():
    problems = validate_example(make(slab="12"))
    assert any("abolished" in p for p in problems)


def test_unknown_slab_is_rejected():
    assert any("not in" in p for p in validate_example(make(slab="7")))


def test_answerable_must_agree_with_slab():
    assert any(
        "answerable=true but slab is UNANSWERABLE" in p
        for p in validate_example(make(slab=UNANSWERABLE))
    )
    assert any(
        "answerable=false but slab" in p
        for p in validate_example(make(answerable=False))
    )


def test_unanswerable_row_needs_a_reason_code():
    ex = make(
        slab=UNANSWERABLE,
        answerable=False,
        difficulty="out_of_scope",
        hsn4="8711",
        labeller_notes="",
    )
    assert any("reason=" in p for p in validate_example(ex))

    ex.labeller_notes = "reason=rate-fact-absent; missing=engine_capacity_cc"
    assert validate_example(ex) == []


def test_unanswerable_row_rejects_unknown_reason():
    ex = make(
        slab=UNANSWERABLE,
        answerable=False,
        difficulty="out_of_scope",
        labeller_notes="reason=dunno",
    )
    assert any("unknown unanswerable reason" in p for p in validate_example(ex))


def test_hsn_must_be_four_digits():
    assert any("4-digit" in p for p in validate_example(make(hsn4="110")))
    assert any("missing hsn4" in p for p in validate_example(make(hsn4=None)))


def test_out_of_scope_family_is_flagged():
    ex = make(input="Ambuja Cement OPC 53 grade, 50 kg bag")
    assert any("out-of-scope family" in p for p in validate_example(ex))


def test_bad_id_format():
    assert any("gst-NNNN" in p for p in validate_example(make(id="rent-0042")))


@pytest.mark.parametrize(
    "existing,expected",
    [([], "gst-0001"), (["gst-0001", "gst-0007"], "gst-0008")],
)
def test_next_id(existing, expected):
    assert next_id([make(id=i) for i in existing]) == expected


def test_round_trip_preserves_fields():
    ex = make()
    assert Example.from_json(ex.to_json()).to_json() == ex.to_json()


def test_deprecated_row_is_inactive():
    assert make().is_active
    assert not make(deprecated_by="gst-0099").is_active
