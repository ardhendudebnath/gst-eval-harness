"""The judge rubric, verdict parsing, and calibration reporting.

No model is called. What is pinned is the contract: the rubric asks the right
question, the parser cannot be fooled by "not a PASS", and the report tells the
truth about a bad κ rather than burying it.
"""

import json

import pytest

from harness.calibration.judge_calibration import Pair, load_pairs, report
from harness.scorers.judge import (
    RUBRIC_VERSION,
    Verdict,
    build_prompt,
    parse_verdict,
)


# --- the rubric asks the right question -----------------------------------


def test_rubric_carries_the_gold_answer_and_the_goods():
    p = build_prompt("Quartz slabs, 92% crushed quartz", "6810", "18", "It is 18%.")
    assert "6810" in p and "18" in p and "Quartz slabs" in p


def test_rubric_fails_right_answer_wrong_route():
    # guideline.md WE-5: "5% because gift hampers are 5%" is the right number
    # by a route that gets the next hamper wrong.
    p = build_prompt("hamper", "0802", "5", "x")
    assert "right number by a route that would fail" in p
    assert "right answer for the wrong reason is a FAIL" in p.lower() or \
           "A right answer for the wrong reason is a FAIL." in p


def test_rubric_rejects_superseded_authority():
    p = build_prompt("x", "9608", "18", "y")
    assert "1/2017" in p and "12%" in p and "28%" in p


def test_rubric_protects_odd_phrasing():
    # A known judge failure mode is penalising sound reasoning worded unusually.
    p = build_prompt("x", "9608", "18", "y")
    assert "not the phrasing" in p
    assert "terse" in p


def test_missing_justification_is_stated_not_blank():
    assert "(the model gave no explanation)" in build_prompt("x", "9608", "18", "")


def test_rubric_is_versioned_and_marked_provisional():
    assert "provisional" in RUBRIC_VERSION


# --- verdict parsing ------------------------------------------------------


def test_parses_pass_and_fail():
    assert parse_verdict("VERDICT: PASS\nREASON: sound").passed is True
    assert parse_verdict("VERDICT: FAIL\nREASON: circular").passed is False


def test_fail_wins_when_both_words_appear():
    # "FAIL, not a PASS" must not be read as a pass.
    assert parse_verdict("VERDICT: FAIL, not a PASS").passed is False
    assert parse_verdict("VERDICT: not a PASS - FAIL").passed is False


def test_reason_is_captured():
    v = parse_verdict("VERDICT: FAIL\nREASON: It cites the 12% slab.")
    assert "12%" in v.reason


def test_missing_verdict_line_is_unparseable():
    v = parse_verdict("I think this explanation is fine.")
    assert v.unparseable and v.passed is None


def test_unrecognised_verdict_word_is_unparseable():
    assert parse_verdict("VERDICT: maybe").unparseable


def test_label_is_the_categorical_used_for_kappa():
    assert Verdict(True, "").label == "PASS"
    assert Verdict(False, "").label == "FAIL"
    assert Verdict(None, "", unparseable=True).label == "UNPARSEABLE"


def test_verdict_records_its_rubric_version():
    assert parse_verdict("VERDICT: PASS").rubric_version == RUBRIC_VERSION


# --- calibration report ---------------------------------------------------


def pair(eid, human, judge) -> Pair:
    return Pair(
        example_id=eid, human=human, judge=judge,
        description="pen tips and balls", gold_slab="18", gold_hsn="9608",
        justification="Heading 9608, Schedule II.", judge_reason="sound",
    )


def test_no_pairs_reports_honestly():
    assert "No paired verdicts yet" in report([])


def test_report_states_kappa_and_the_matrix():
    pairs = [pair(f"gst-{i:04d}", "PASS", "PASS") for i in range(8)]
    pairs += [pair("gst-0009", "FAIL", "FAIL"), pair("gst-0010", "FAIL", "PASS")]
    out = report(pairs, "claude-opus-5")
    assert "Cohen's κ" in out
    assert "Confusion matrix" in out
    assert "claude-opus-5" in out
    assert RUBRIC_VERSION in out


def test_unusable_kappa_is_called_out_not_buried():
    # Perfect disagreement: the report must say the judge is unusable.
    pairs = [pair(f"gst-{i:04d}", "PASS", "FAIL") for i in range(5)]
    pairs += [pair(f"gst-1{i:03d}", "FAIL", "PASS") for i in range(5)]
    out = report(pairs)
    assert "unusable" in out.lower()
    assert "result, not a blocker to hide" in out


def test_direction_of_error_is_separated():
    pairs = [pair("a", "FAIL", "PASS"), pair("b", "FAIL", "PASS"),
             pair("c", "PASS", "FAIL"), pair("d", "PASS", "PASS")]
    out = report(pairs)
    assert "too lenient" in out and "too strict" in out
    assert "fluent-but-unsound" in out  # lenient > strict, so this diagnosis


def test_every_disagreement_is_listed_with_context():
    out = report([pair("gst-0042", "FAIL", "PASS"), pair("gst-0001", "PASS", "PASS")])
    assert "gst-0042" in out
    assert "pen tips and balls" in out
    assert "Heading 9608" in out


def test_categories_are_suggested_not_assigned():
    out = report([pair("gst-0042", "FAIL", "PASS")])
    assert "**category:** _TODO_" in out
    assert "fluent-but-wrong" in out  # offered as vocabulary


def test_perfect_agreement_warns_about_triviality():
    out = report([pair(f"gst-{i:04d}", "PASS", "PASS") for i in range(6)])
    assert "trivially easy" in out


# --- joining judge verdicts to human labels -------------------------------


def test_pairs_only_where_a_human_label_exists(tmp_path):
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text(
        json.dumps({"example_id": "a", "verdict": "PASS"}) + "\n"
        + json.dumps({"example_id": "b", "verdict": "FAIL"}) + "\n",
        encoding="utf-8",
    )
    human = tmp_path / "h.jsonl"
    human.write_text(json.dumps({"example_id": "a", "verdict": "fail"}) + "\n",
                     encoding="utf-8")

    pairs = load_pairs(verdicts, human)
    assert [p.example_id for p in pairs] == ["a"]
    assert pairs[0].human == "FAIL"  # case-normalised
    assert not pairs[0].agree


def test_no_human_labels_yields_no_pairs(tmp_path):
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text(json.dumps({"example_id": "a", "verdict": "PASS"}) + "\n",
                        encoding="utf-8")
    assert load_pairs(verdicts, tmp_path / "absent.jsonl") == []


def test_kappa_reuses_the_self_agreement_implementation():
    # The judge is held to exactly the measure the human was — that is the
    # point of calibration.
    from harness.calibration import judge_calibration, kappa

    assert judge_calibration.cohens_kappa is kappa.cohens_kappa
