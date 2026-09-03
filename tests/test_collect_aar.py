"""Tests for the AAR collector.

Fixtures reproduce the *structure* of real rulings on gstcouncil.gov.in —
the labelled-table header, the section ordering, and the OCR damage — because
the parser has to cope with what the source actually emits rather than an
idealised version of it.

Party details are synthetic throughout: `ABCDE1234F` is the standard
placeholder PAN used in Indian tax documentation, and the companies, addresses
and names below are invented. The rulings these were modelled on are public,
but `data/DATA_LICENCE.md` §1.2 commits to stripping party-identifying detail,
and a test suite that shipped real names while asserting they get stripped
would contradict that.
"""

import pytest

from harness.collect.aar import (
    _hsn_candidates,
    _stale_rates,
    dedupe_key,
    extract_pdf_text,
    is_about_services,
    is_classification,
    is_scanned,
    parse_index_page,
    segment_goods_description,
)
from harness.collect.normalise import normalise

# West Bengal-style layout: a labelled table rather than prose, which is how
# applicant names and postal addresses were reaching the pool unredacted.
# The truncated opening word is faithful — segmentation used to start mid-word
# here. Party details are invented.
WB_TEXT = """y such Appeal shall be filed in accordance with Section 100 (3) of
the GST Act and the Rules prescribed thereunder, and the Regulations prescribed
by the West Bengal Authority for Advance Ruling Regulations, 2018.
Name of the applicant Examplco Pharma Pvt Ltd Address Suite No. 101, Sample
Tower, 4th floor, Kolkata - 700099 GSTIN Case Number 06 of 2019
ARN AD1901190000000 Date of application January 25, 2019
Order number and date 46/WBAAR/2018-19 dated 26/03/2019
Applicant's representative heard A. N. Example, Advocate
1. Admissibility of the Application
1.1 The Applicant is stated to be a manufacturer of pharmaceuticals, APIs and
other medicaments. He seeks a ruling on classification of fifteen products
which are food supplements containing vitamins and minerals.
DISCUSSION AND FINDINGS
The products are classifiable under HSN 2106.
"""

# An index row with the cell classes the parser keys on.
INDEX_HTML = """
<table class="table table-bordered customdatatable">
<tr><th>Sr. No.</th><th>Name of the Applicant</th></tr>
<tr>
<td headers="a" class="views-field views-field-counter">1</td>
<td headers="b" class="views-field views-field-title">M/s Examplco Cryogenics Pvt. Ltd.</td>
<td headers="c" class="views-field views-field-field-states-ut">Gujarat</td>
<td headers="d" class="views-field views-field-body"><p>Whether supply of Cryo
Container is classifiable under HSN 7613 0019 or HSN 9617 0012?</p></td>
<td headers="e" class="views-field views-field-field-order-no-date">GUJ/GAAR/R/2018/10, dated 09.04.2018</td>
<td headers="f" class="views-field views-field-field-upload-file">
<p><a href="/sites/default/files/AAR/guj.gaar.r.2018-10.pdf">Download</a></p></td>
<td headers="g" class="views-field views-field-field-category">97(2) (a)</td>
</tr>
</table>
"""

# Real extracted text, including the OCR mangling seen in the source.
RULING_TEXT = """THE AUTHORITY FOR ADVANCE RULING IN GUJARAT
GOODS AND SERVICE TAX

1. Name and address of the applicant

Brief facts:
M/s. Examplco Seed Products (for short-'applicant'), 1, Sample
Estate, Ahmedabad, Gujarat- 380 099, is a
partnership firm & their GSTIN number is 24ABCDE1234FlZU.
2. The applicant deals in various types of seed mix, two of which are 'Mix
mukhwas' and 'Roasted til & ajwain', which they claim is made up of mixed
roasted and salted seeds. The applicant submits that the goods merit
classification under tariff item 1207 40 90 and are chargeable at 5%.

DISCUSSION AND FINDINGS
We have considered the submissions made by the applicant. The heading 2106
covers food preparations not elsewhere specified.

RULING
The products are classifiable under HSN 2106 90 99 and attract 12% GST.
"""


# --- index parsing --------------------------------------------------------


def test_parse_index_row():
    rows = parse_index_page(INDEX_HTML)
    assert len(rows) == 1  # the <th> header row is skipped
    row = rows[0]
    assert row["applicant"] == "M/s Examplco Cryogenics Pvt. Ltd."
    assert row["state"] == "Gujarat"
    assert row["category"] == "97(2) (a)"
    assert row["pdf"] == "/sites/default/files/AAR/guj.gaar.r.2018-10.pdf"
    assert "Cryo Container" in row["brief"]


def test_parse_index_page_without_rows():
    assert parse_index_page("<table><tr><th>Sr. No.</th></tr></table>") == []


# --- classification filter ------------------------------------------------


@pytest.mark.parametrize(
    "category",
    ["97(2) (a)", "97(2)(a)", "97 (2) (a)", "97(2)(a),(b)", "97(2) (a), (e)", "97 (2) (a) (e)"],
)
def test_clause_a_is_recognised_in_every_written_form(category):
    # The Council writes the clause list half a dozen different ways.
    assert is_classification({"category": category, "brief": ""})


@pytest.mark.parametrize("category", ["97(2) (b)", "97(2)(e)", "97 (2) (d)"])
def test_other_clauses_are_not_classification(category):
    assert not is_classification({"category": category, "brief": "e-invoicing applies"})


def test_brief_keywords_rescue_a_blank_category():
    assert is_classification(
        {"category": "97(2)", "brief": "Under which HSN code should this be classified?"}
    )


def test_unrelated_ruling_is_excluded():
    assert not is_classification(
        {"category": "97(2)", "brief": "Whether the transfer of a business as a going concern is a supply"}
    )


# --- goods vs services ----------------------------------------------------
#
# s.97(2)(a) is "classification of any goods OR SERVICES or both", so the
# clause alone does not select goods. These are real briefs that the clause
# filter alone let through.


@pytest.mark.parametrize(
    "brief",
    [
        "Whether supply of construction service bundled with preferential location"
        " service is a composite supply",
        "Classification and rates of tax on the services supplied by the club",
        "Whether repairing of transformers is composite supply and what will be the"
        " applicable rate of tax",
        "Whether the activity of job work on goods amounts to supply",
        "GST rate on renting of immovable property",
    ],
)
def test_services_rulings_are_rejected_despite_clause_a(brief):
    row = {"category": "97(2) (a)", "brief": brief}
    assert is_about_services(row)
    assert not is_classification(row)


@pytest.mark.parametrize(
    "brief",
    [
        "Classification of food supplements",
        "Whether the seeds qualify as fresh or dried",
        "Whether truck mounted cranes fall under chapter heading 8426 or 8705",
        "Whether Cryo Container is classifiable under HSN 7613 0019 or 9617 0012",
    ],
)
def test_goods_rulings_survive_the_services_screen(brief):
    row = {"category": "97(2) (a)", "brief": brief}
    assert not is_about_services(row)
    assert is_classification(row)


@pytest.mark.parametrize(
    "brief",
    [
        # All three reached the pool in a live run: an activity can be a service
        # without the brief ever using the word "service".
        "Whether lodging along with food to the students by a private boarding"
        " house is a composite supply",
        "The applicant is printing content provided by the customers."
        " Classification of the nature of the activity",
        "The applicability of GST for invoices raised for storage charges for"
        " storing their imported goods",
    ],
)
def test_service_activities_without_the_word_service_are_rejected(brief):
    assert is_about_services({"brief": brief})


def test_printed_goods_are_not_confused_with_printing_services():
    # "printed advertisement materials" asks whether the output is goods;
    # "printing content" describes an activity. Only the latter is a service.
    assert not is_about_services({"brief": "Whether printed advertisement materials are goods"})


# --- services identifiable only from the facts ----------------------------


def test_works_contract_named_in_the_facts_not_the_brief():
    # Real leak: the brief cites a notification entry and never says "service";
    # only the facts say "composite supply of works contract".
    brief = (
        "The issue relates to applicability of Entry 3(vi) of Notification "
        "No.11/2017-CT(Rate) dated 28.06.2017 & determination of transaction value."
    )
    facts = (
        "The applicant has submitted that the entire contract shall be treated as a "
        "contract for the composite supply of works contract involving a supply of "
        "goods and services."
    )
    assert is_about_services({"brief": brief}, facts)


def test_services_rate_notification_is_a_service_signal():
    # 11/2017-CT(Rate) prescribes rates for services; goods are 1/2017, now 9/2025.
    assert is_about_services({"brief": "Applicability of Entry 3(vi) of Notification 11/2017-CT(Rate)"})


def test_goods_rate_notification_is_not_a_service_signal():
    assert not is_about_services(
        {"brief": "Classification under Sl. No. 192 of Schedule II of Notification 1/2017-CT(Rate)"}
    )


@pytest.mark.parametrize(
    "brief",
    [
        "Whether EPC Contract in respect of power distribution falls under Government Entity",
        "Erection, Testing and Commissioning of substations on turnkey basis",
    ],
)
def test_works_contract_vocabulary_is_caught(brief):
    assert is_about_services({"brief": brief})


def test_goods_ruling_with_facts_still_passes():
    brief = "What is the Classification as per HSN and rate of tax on Pallets and Box Pallets"
    facts = (
        "The Applicant is a private limited company engaged in the manufacture of "
        "plywood pallets, plywood boxes, corrugated boxes and paper packaging products."
    )
    assert not is_about_services({"brief": brief}, facts)


# --- false positives that dropped real goods rulings ----------------------
#
# Every case below is text from a genuine goods ruling that a naive screen
# rejected. The tax is the "Goods and Services Tax", so weak vocabulary in the
# 1,200-word facts is noise, not signal.


@pytest.mark.parametrize(
    "facts",
    [
        # The statute's own name, present in every single ruling.
        "registered under the Goods and Services Act, 2017. He is desirous of "
        "knowing the GST rate applicable on the finished goods Pallets.",
        "prior to introduction of Goods and Service Tax Act, the polypropylene "
        "non-woven bags were being classified under heading No. 6305.",
        # "catering to" is a verb phrase, not food service.
        "manufacture and supply of High Precision Components and Assemblies, "
        "catering to a global clientele in the automotive and aerospace sectors.",
        # "storage" describing what goods do or where they sit.
        "the resulting material is put in storage bins which is in the "
        "semi-finished stage of manufacture of poultry meal.",
        "used as liners for water ponds and canals, for storage of water bodies "
        "in states with scanty rainfall.",
        # Boilerplate recital of what GST is levied on.
        "Applicant understands that GST is a tax to be levied on supply of goods "
        "and/or services under the Act.",
    ],
)
def test_weak_vocabulary_in_the_facts_does_not_reject_goods(facts):
    assert not is_about_services({"brief": "Classification of goods"}, facts)


@pytest.mark.parametrize(
    "brief",
    [
        # Government-entity status is a Notification 11/2017 concessional-rate
        # concept, so a ruling turning on it is a works-contract ruling.
        "Whether APEPDCL can be treated as a limb of Government of AP or not? "
        "What is the rate of tax of the work executed and under which SAC/HSN code",
        "GSRDC is a Government Entity. In addition, GSRDC shall also be a "
        "Government Authority, in such case what is the rate",
        "Whether the above work of APIIC executed by the applicant after "
        "22.08.2017 falls under the 18% rate of tax or 12% rate of tax?",
        "composite supply of works contract provided to a government authority "
        "or a Government Entity having GST rate of 5%",
    ],
)
def test_government_entity_rulings_are_rejected(brief):
    assert is_about_services({"brief": brief})


def test_ordinary_government_supply_is_not_rejected():
    # Supplying goods to a government buyer is not a works contract.
    assert not is_about_services(
        {"brief": "Classification of stationery supplied to a government school"}
    )


def test_weak_vocabulary_in_the_brief_still_rejects():
    # The same word is trustworthy in the Council's curated one-liner.
    assert is_about_services({"brief": "Classification of storage services provided"})


def test_statute_name_in_the_brief_is_also_neutralised():
    assert not is_about_services(
        {"brief": "Classification of pallets under the Goods and Services Tax Act"}
    )


# --- content dedupe -------------------------------------------------------


def test_same_ruling_under_two_filenames_collides():
    # A Cryo Container ruling was published twice under different filenames;
    # source_id dedupe alone let both into the pool.
    a = "The applicant submits that the Cryo Container, also known as Liquid Nitrogen Container, is made of aluminium."
    b = "The  applicant  submits that the CRYO CONTAINER, also known as liquid nitrogen container, is made of aluminium!"
    assert dedupe_key(a) == dedupe_key(b)


def test_different_rulings_do_not_collide():
    assert dedupe_key("Quartz slabs of crushed quartz") != dedupe_key("Polypropylene mats plaited")


# --- file size ------------------------------------------------------------


def test_index_row_reports_pdf_size():
    html = INDEX_HTML.replace(
        '<td headers="f" class="views-field views-field-field-upload-file">',
        '<td headers="f" class="views-field views-field-field-upload-file">'
        "(Format: pdf, Size: 2.01 MB)",
    )
    assert parse_index_page(html)[0]["size_mb"] == pytest.approx(2.01)


def test_missing_size_is_none_not_zero():
    # None means "unknown, download it"; 0 would wrongly skip everything.
    assert parse_index_page(INDEX_HTML)[0]["size_mb"] is None


# --- scanned detection ----------------------------------------------------


def test_scanned_pdf_is_detected():
    # Observed real case: 4 pages yielding 3 characters.
    assert is_scanned("   ", 4)
    assert is_scanned("", 24)


def test_text_pdf_is_not_scanned():
    # Observed real case: ~2000 chars/page.
    assert not is_scanned("x" * 12_000, 6)


def test_zero_pages_counts_as_scanned():
    assert is_scanned("anything", 0)


def test_unparseable_bytes_yield_no_text():
    # The only test here that needs the optional collect extra; everything else
    # exercises pure parsing and runs on a bare clone.
    pytest.importorskip("pypdf")
    text, pages = extract_pdf_text(b"not a pdf at all")
    assert text == "" and pages == 0


# --- segmentation ---------------------------------------------------------


def test_excerpt_starts_at_brief_facts_and_stops_before_the_answer():
    excerpt, truncated = segment_goods_description(RULING_TEXT, 300)
    assert "seed mix" in excerpt
    assert "Mix" in excerpt
    assert not truncated
    # The authority's reasoning and the ruling must not leak in — they contain
    # the answer this benchmark is asking the model for.
    assert "DISCUSSION" not in excerpt
    assert "2106 90 99" not in excerpt
    assert "12% GST" not in excerpt


def test_applicants_own_proposed_heading_is_kept():
    # The applicant argues 1207 40 90; the authority rejects it for 2106.
    # Keeping the rejected contention is what makes these adversarial examples.
    excerpt, _ = segment_goods_description(RULING_TEXT, 300)
    assert "1207 40 90" in excerpt


def test_word_cap_truncates_and_reports_it():
    long_text = "Brief facts: " + ("widget " * 500) + "DISCUSSION"
    excerpt, truncated = segment_goods_description(long_text, 100)
    assert truncated
    assert len(excerpt.split()) == 100


def test_west_bengal_layout_is_segmented_at_the_right_place():
    excerpt, _ = segment_goods_description(WB_TEXT, 300)
    assert excerpt.startswith("The Applicant is stated to be")
    assert "food supplements" in excerpt
    # Appeal boilerplate and the answer both stay out.
    assert "Appeal shall be filed" not in excerpt
    assert "HSN 2106" not in excerpt


def test_unlocatable_facts_section_returns_none():
    # Refusing beats guessing: the old fixed-offset fallback produced excerpts
    # that began mid-word inside appeal boilerplate.
    assert segment_goods_description("x" * 2000 + " RULING the answer", 300) is None


def test_excerpt_below_minimum_length_returns_none():
    assert segment_goods_description("Brief facts: A widget. DISCUSSION", 300) is None


# --- metadata extraction --------------------------------------------------


def test_hsn_candidates_are_normalised_and_deduped():
    codes = _hsn_candidates(RULING_TEXT)
    assert "12074090" in codes
    assert "21069099" in codes


@pytest.mark.parametrize(
    "text", ["Customs Tariff Act, 1975", "the CTA, 1985 applies", "Tariff heading 2017"]
)
def test_statute_years_are_not_mistaken_for_headings(text):
    # No HSN chapter reaches 19, so a 4-digit code starting 19 or 20 is a year.
    assert _hsn_candidates(text) == []


def test_eight_digit_code_starting_with_20_is_kept():
    # 2008 19 90 is a real heading (prepared nuts) — only bare 4-digit years go.
    assert "20081990" in _hsn_candidates("classifiable under HSN 2008 19 90")


def test_stale_rates_keeps_only_plausible_slabs():
    rates = _stale_rates(RULING_TEXT)
    assert "5" in rates and "12" in rates
    # 12% is abolished, which is precisely why it is recorded and never copied.
    assert "97" not in _stale_rates("97% of respondents")


# --- redaction on real OCR damage -----------------------------------------


def test_ocr_mangled_gstin_is_stripped():
    # Real ruling GSTINs come back from OCR with letter l substituted for
    # digit 1, which the strict 15-character GSTIN grammar does not match.
    cleaned, applied = normalise(RULING_TEXT, is_ruling=True)
    assert "24ABCDE1234FlZU" not in cleaned
    assert "strip_gstin" in applied


def test_applicant_name_followed_by_bracket_is_stripped():
    cleaned, applied = normalise(RULING_TEXT, is_ruling=True)
    assert "Examplco Seed Products" not in cleaned
    assert "strip_applicant" in applied
    # The goods survive redaction — that is the part being benchmarked.
    assert "seed mix" in cleaned


def test_labelled_table_applicant_and_address_are_stripped():
    # Several authorities name the applicant in a table field with no "M/s"
    # prefix, which is how names and postal addresses reached the pool intact.
    cleaned, applied = normalise(WB_TEXT, is_ruling=True)
    assert "Examplco Pharma" not in cleaned
    assert "Sample Tower" not in cleaned
    assert "700099" not in cleaned
    assert "strip_applicant_field" in applied
    assert "strip_address_field" in applied


def test_arn_and_representative_name_are_stripped():
    cleaned, applied = normalise(WB_TEXT, is_ruling=True)
    assert "AD1901190000000" not in cleaned
    assert "A. N. Example" not in cleaned
    assert "strip_arn" in applied
    assert "strip_representative" in applied


def test_redaction_leaves_the_goods_intact():
    cleaned, _ = normalise(WB_TEXT, is_ruling=True)
    assert "food supplements" in cleaned
    assert "vitamins and minerals" in cleaned


# --- procedural furniture -------------------------------------------------
#
# Real boilerplate observed in collected rulings. It carries no classification
# signal and pads every input, which would inflate cost-per-correct-answer.

FURNITURE_TEXT = (
    "The Applicant manufactures Kalava Raksha Sutra (Sacred Thread), tied on the "
    "wrist with different colours and sold in Kilograms. Page 1 of 8 "
    "Note : Any Appeal against the Advance Ruling order shall be filed before the "
    "Tamilnadu State Appellate Authority for Advance Ruling, Chennai under "
    "Sub-section (1) of Section 100 of CGST Act within 30 days from the date on "
    "which the ruling sought to be appealed against is communicated. "
    "Advance ruling is admissible on classification of any goods or services or "
    "both under section 97(2)(a) of the GST Act."
)


def test_page_markers_are_stripped():
    cleaned, applied = normalise(FURNITURE_TEXT, is_ruling=True)
    assert "Page 1 of 8" not in cleaned
    assert "strip_page_marker" in applied


def test_appeal_notice_is_stripped():
    cleaned, applied = normalise(FURNITURE_TEXT, is_ruling=True)
    assert "Appellate Authority" not in cleaned
    assert "30 days" not in cleaned
    assert "strip_appeal_notice" in applied


def test_admissibility_recital_is_stripped():
    cleaned, applied = normalise(FURNITURE_TEXT, is_ruling=True)
    assert "97(2)(a)" not in cleaned
    assert "strip_admissibility_recital" in applied


def test_furniture_stripping_preserves_the_goods():
    cleaned, _ = normalise(FURNITURE_TEXT, is_ruling=True)
    assert "Kalava Raksha Sutra" in cleaned
    assert "sold in Kilograms" in cleaned
    # Roughly two thirds of that input was procedural padding.
    assert len(cleaned) < len(FURNITURE_TEXT) * 0.5


def test_furniture_patterns_do_not_fire_on_plain_goods_text():
    _, applied = normalise("Quartz slabs made of 92% crushed quartz.", is_ruling=True)
    assert applied == []
