"""The prompt contract and the parser for what models send back.

The parser must be forgiving about formatting and unforgiving about meaning.
In particular it must preserve an abolished rate exactly as stated — a model
answering 12% is the finding, so silently normalising it away would delete the
result the benchmark exists to produce.
"""

import pytest

from harness.prompt import PROMPT_VERSION, build, parse


def test_prompt_carries_the_description():
    p = build("Tata Salt Iodised, 1 kg pouch")
    assert "Tata Salt Iodised, 1 kg pouch" in p


def test_prompt_offers_only_valid_slabs():
    from harness.schema import ABOLISHED_SLABS

    p = build("x")
    for dead in ABOLISHED_SLABS:
        assert f" {dead}," not in p, f"prompt must not offer abolished slab {dead}"
    assert "UNANSWERABLE" in p


def test_prompt_is_versioned():
    assert PROMPT_VERSION


# --- well-formed answers --------------------------------------------------


def test_parses_the_documented_format():
    out = parse(
        "SLAB: 18\nHSN: 9608\nANSWERABLE: yes\n"
        "WHY: Pen parts, heading 9608, Schedule II."
    )
    assert out.slab == "18"
    assert out.hsn4 == "9608"
    assert out.answerable is True
    assert "Schedule II" in out.justification
    assert not out.unparseable


@pytest.mark.parametrize(
    "line,expected",
    [
        ("SLAB: 18", "18"),
        ("SLAB: 18%", "18"),
        ("SLAB: 18 percent", "18"),
        ("SLAB:18", "18"),
        ("slab - 18", "18"),
        ("SLAB:  18.0 ", "18"),
        ("SLAB: 0.25", "0.25"),
        ("SLAB: UNANSWERABLE", "UNANSWERABLE"),
    ],
)
def test_slab_formatting_variants(line, expected):
    assert parse(line + "\nHSN: NONE").slab == expected


def test_hsn_none_is_no_heading():
    assert parse("SLAB: 5\nHSN: NONE").hsn4 is None
    assert parse("SLAB: 5\nHSN: N/A").hsn4 is None


def test_hsn_extracted_from_a_longer_code():
    assert parse("SLAB: 18\nHSN: 9608 99 90").hsn4 == "9608"


def test_answerable_inferred_when_the_line_is_missing():
    assert parse("SLAB: 5\nHSN: 1101").answerable is True
    assert parse("SLAB: UNANSWERABLE\nHSN: 8711").answerable is False


# --- the finding must survive parsing ------------------------------------


@pytest.mark.parametrize("dead", ["12", "28"])
def test_abolished_rates_are_preserved_not_corrected(dead):
    # The parser records what the model said. Deciding it is wrong is the
    # scorer's job, and quietly fixing it here would erase the finding.
    assert parse(f"SLAB: {dead}\nHSN: 9608").slab == dead


# --- malformed answers ----------------------------------------------------


def test_missing_slab_line_is_unparseable():
    out = parse("I think this is probably eighteen percent.")
    assert out.unparseable
    assert out.slab is None


def test_empty_response_is_unparseable():
    assert parse("").unparseable


def test_preamble_before_the_answer_is_tolerated():
    out = parse(
        "Sure, here is my classification.\n\nSLAB: 5\nHSN: 1101\nANSWERABLE: yes\n"
    )
    assert out.slab == "5" and out.hsn4 == "1101"


def test_slab_line_with_no_number_and_no_sentinel():
    assert parse("SLAB: it depends\nHSN: NONE").slab is None
