"""Extracting what the authority decided from the operative ruling.

Fixtures reproduce the shape of real orders, including the spaced "R U L I N G"
heading and the Q/Ans layout. Party details are synthetic.
"""

from harness.collect.ruling_outcome import (
    TAIL_FRACTION,
    extract_outcome,
    find_operative_ruling,
)

PREAMBLE = (
    "THE AUTHORITY FOR ADVANCE RULING. The applicant sought a ruling on the "
    "following question: Whether the goods are classifiable under Heading 1234? "
    + ("Discussion of the submissions and the tariff follows here. " * 30)
)

# Real orders close with a signature block, so an operative ruling always has
# a few hundred characters after the heading. MIN_TAIL_CHARS relies on that.
SIGN_OFF = (
    " This ruling is valid subject to the provisions under Section 103 of the Act. "
    "(Member, Central Tax) (Member, State Tax) Place: Sampletown Date: 01.01.2019"
)

DETERMINATION = (
    " R U L I N G The goods supplied by the applicant are to be classified under "
    "GST Tariff Heading 9608 99 90 and included under Sl No. 453 of Schedule III "
    "of Notification No. 01/2017-Central Tax (Rate) dated 28.06.2017." + SIGN_OFF
)


def test_finds_the_operative_ruling():
    quote = find_operative_ruling(PREAMBLE + DETERMINATION)
    assert quote is not None
    assert "9608 99 90" in quote


def test_heading_is_extracted_and_normalised():
    out = extract_outcome(PREAMBLE + DETERMINATION)
    assert out is not None
    assert "96089990" in out.headings


def test_statute_year_is_not_read_as_a_heading():
    out = extract_outcome(PREAMBLE + DETERMINATION)
    assert "2017" not in out.headings
    assert "0117" not in out.headings


def test_question_section_alone_is_not_the_ruling():
    # Without a determination anywhere, nothing should be returned.
    assert find_operative_ruling(PREAMBLE) is None


def test_early_determination_language_is_ignored():
    # The same sentence placed early is discussion, not the operative ruling.
    early = DETERMINATION + (" Further discussion of the matter follows. " * 60)
    assert find_operative_ruling(early) is None


def test_tail_fraction_is_a_sane_bound():
    assert 0.3 < TAIL_FRACTION < 0.9


# --- confidence signals ---------------------------------------------------


def test_conditional_determination_is_flagged():
    text = PREAMBLE + (
        " R U L I N G The products are appropriately classifiable under Heading 3307 "
        "or 3401 depending upon their constituents." + SIGN_OFF
    )
    out = extract_outcome(text)
    assert out.is_conditional
    assert set(out.headings) == {"3307", "3401"}
    assert "conditional" in out.confidence


def test_restated_question_is_demoted():
    # Real misfire: the passage read like a determination but was the question.
    text = PREAMBLE + (
        " R U L I N G from the honourable authority on the question as to whether the "
        "printed advertisement materials are classifiable under chapter heading 4911 "
        "of the first schedule to the Customs Tariff Act? Any clarification thereon."
        + SIGN_OFF
    )
    out = extract_outcome(text)
    assert out.looks_like_question
    assert "low" in out.confidence


def test_question_followed_by_an_answer_is_not_demoted():
    # "Q.1 Whether ... ? Ans. ..." is a real ruling layout.
    text = PREAMBLE + (
        " R U L I N G Q.1 Whether the Non Woven Bags are classifiable under Heading "
        "6305 or under Heading 3923? Ans. The product is classifiable under Heading 6305."
        + SIGN_OFF
    )
    out = extract_outcome(text)
    assert not out.looks_like_question


def test_split_cgst_rate_is_combined():
    text = PREAMBLE + (
        " R U L I N G The goods are classifiable under chapter heading 4911 and the "
        "rate of tax applicable is 6% CGST + 6% SGST." + SIGN_OFF
    )
    out = extract_outcome(text)
    # 6+6 is the abolished 12% slab, which is exactly why the rate is a trap.
    assert out.combined_rate_hint == "12"


def test_negative_determination_is_still_returned():
    text = PREAMBLE + (
        " R U L I N G The product would not be covered by Sl. No. 192 of Schedule II "
        "of Notification No. 1/2017-Central Tax (Rate)." + SIGN_OFF
    )
    out = extract_outcome(text)
    assert out is not None
    assert "would not be covered" in out.quote


def test_returns_none_when_there_is_no_ruling_at_all():
    assert extract_outcome("An unrelated document with no ruling in it.") is None


# --- redaction ------------------------------------------------------------


def test_quote_is_redacted():
    # The operative ruling names the applicant and, in one real order, quoted a
    # live GSTIN. This passage never passes through the collector's pipeline,
    # so it must be redacted where it is produced.
    text = PREAMBLE + (
        " R U L I N G The products supplied by M/s. Examplco Filaments Limited "
        "(GSTIN 24ABCDE1234F1Z5) are appropriately classifiable under Heading 3307."
        + SIGN_OFF
    )
    out = extract_outcome(text)
    assert out is not None
    assert "24ABCDE1234F1Z5" not in out.quote
    assert "Examplco Filaments" not in out.quote


def test_redaction_keeps_the_determination_intact():
    text = PREAMBLE + (
        " R U L I N G The products supplied by M/s. Examplco Filaments Limited "
        "(GSTIN 24ABCDE1234F1Z5) are appropriately classifiable under Heading 3307."
        + SIGN_OFF
    )
    out = extract_outcome(text)
    assert "3307" in out.headings
    assert "classifiable" in out.quote
