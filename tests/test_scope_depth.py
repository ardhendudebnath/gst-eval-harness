"""Scope screening must judge a ruling's subject, not stray words inside it.

Raising the excerpt cap from 300 to 1200 words made whole-text screening wrong:
a long ruling about industrial machinery that mentions a cement plant as a
customer is not a ruling about cement, but a whole-text match discards it.
"""

from harness.collect.aar import SCOPE_HEAD_WORDS, scope_text
from harness.schema import out_of_scope_term

MACHINERY_RULING = (
    "The applicant manufactures rotary kilns and material handling conveyors "
    "for industrial plants, and seeks a ruling on their classification. "
    + ("The equipment is fabricated from steel sections. " * 60)
    + "Such plants are also supplied to customers distilling rum."
)


def test_incidental_mention_deep_in_a_long_ruling_is_not_topical():
    brief = "Classification of rotary kilns and conveyors"
    # The bare text does contain the term...
    assert out_of_scope_term(MACHINERY_RULING) == "rum"
    # ...but it is not what the ruling is about, so screening must not fire.
    assert out_of_scope_term(scope_text(MACHINERY_RULING, brief)) is None


def test_topical_mention_in_the_brief_still_fires():
    brief = "Classification of and rate of tax on beer manufactured by the applicant"
    assert out_of_scope_term(scope_text("The applicant manufactures a product.", brief))


def test_topical_mention_in_the_opening_facts_still_fires():
    excerpt = "The applicant is engaged in the manufacture of beer at its brewery."
    assert out_of_scope_term(scope_text(excerpt, "Classification query")) == "beer"


def test_scope_text_only_reads_the_opening():
    excerpt = " ".join(["filler"] * (SCOPE_HEAD_WORDS + 50)) + " tobacco"
    assert "tobacco" not in scope_text(excerpt)
    assert out_of_scope_term(scope_text(excerpt)) is None


def test_scope_text_includes_the_brief_in_full():
    assert "beer" in scope_text("goods", "Classification of beer")


def test_alcohol_named_up_front_is_still_caught():
    excerpt = "The applicant brews beer at its facility in the state."
    assert out_of_scope_term(scope_text(excerpt, "")) == "beer"
