"""Deterministic scoring, including the stale-slab rate.

The load-bearing behaviours: a failed call scores as wrong rather than being
dropped, and quoting an abolished rate is counted separately from being merely
inaccurate.
"""

import pytest

from harness.prompt import Parsed
from harness.scorers.exact import describe_stale, score_row, summarise
from harness.schema import Example


def gold(slab="18", hsn4="9608", answerable=True) -> Example:
    return Example(
        id="gst-0001",
        input="pen tips and balls",
        slab=slab,
        hsn4=hsn4,
        answerable=answerable,
        justification="Heading 9608, Schedule II.",
        difficulty="hard",
    )


def pred(slab="18", hsn4="9608", answerable=True, unparseable=False) -> Parsed:
    return Parsed(slab, hsn4, answerable, "because", unparseable)


# --- per row --------------------------------------------------------------


def test_exact_match_scores_correct():
    s = score_row(gold(), pred())
    assert s.slab_correct and s.hsn_correct and s.chapter_correct


def test_wrong_slab_scores_wrong():
    assert not score_row(gold(), pred(slab="5")).slab_correct


def test_chapter_partial_credit_without_full_hsn():
    s = score_row(gold(hsn4="9608"), pred(hsn4="9609"))
    assert not s.hsn_correct
    assert s.chapter_correct  # both chapter 96


def test_errored_call_scores_wrong_not_skipped():
    # Dropping errored rows would inflate accuracy for whichever model errors
    # most, which is exactly backwards.
    s = score_row(gold(), pred(), errored=True)
    assert s.errored
    assert not s.slab_correct and not s.abstention_correct


def test_unparseable_answer_scores_wrong():
    s = score_row(gold(), pred(unparseable=True))
    assert s.unparseable and not s.slab_correct


# --- abolished slabs ------------------------------------------------------


@pytest.mark.parametrize("dead", ["12", "28"])
def test_abolished_slab_is_flagged(dead):
    s = score_row(gold(), pred(slab=dead))
    assert s.stale_slab == dead
    assert not s.slab_correct


def test_correct_answer_is_not_flagged_stale():
    assert score_row(gold(), pred()).stale_slab is None


# --- abstention -----------------------------------------------------------


def test_correct_refusal():
    g = gold(slab="UNANSWERABLE", answerable=False)
    s = score_row(g, pred(slab="UNANSWERABLE", answerable=False))
    assert s.slab_correct and s.abstention_correct


def test_answering_an_unanswerable_is_an_abstention_miss():
    g = gold(slab="UNANSWERABLE", answerable=False)
    s = score_row(g, pred(slab="18"))
    assert not s.abstention_correct


def test_refusing_an_answerable_is_also_a_miss():
    s = score_row(gold(), pred(slab="UNANSWERABLE", answerable=False))
    assert not s.abstention_correct


# --- summary --------------------------------------------------------------


def test_summary_rates():
    rows = [
        score_row(gold(), pred()),               # correct
        score_row(gold(), pred(slab="12")),      # stale
        score_row(gold(), pred(slab="28")),      # stale
        score_row(gold(), pred(slab="5")),       # plain wrong
    ]
    s = summarise(rows)
    assert s.n == 4
    assert s.slab_acc == 0.25
    assert s.stale_slab_rate == 0.5
    assert s.stale_by_slab == {"12": 1, "28": 1}


def test_stale_description_names_the_abolition_dates():
    rows = [score_row(gold(), pred(slab="12"))]
    text = describe_stale(summarise(rows))
    assert "2025-09-22" in text


def test_no_stale_reads_cleanly():
    assert describe_stale(summarise([score_row(gold(), pred())])) == (
        "no abolished slab quoted"
    )


def test_abstention_f1_on_a_mixed_run():
    unans = gold(slab="UNANSWERABLE", answerable=False)
    rows = [
        score_row(unans, pred(slab="UNANSWERABLE", answerable=False)),  # tp
        score_row(unans, pred(slab="18")),                              # fn
        score_row(gold(), pred(slab="UNANSWERABLE", answerable=False)), # fp
        score_row(gold(), pred()),                                      # tn
    ]
    s = summarise(rows)
    assert s.abstain_precision == 0.5
    assert s.abstain_recall == 0.5
    assert s.abstain_f1 == pytest.approx(0.5)


def test_empty_run_summarises_to_zero_not_a_crash():
    assert summarise([]).n == 0
