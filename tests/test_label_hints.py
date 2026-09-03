"""The labelling tool must not present the stale rate as an ordinary hint.

Most advance rulings predate 22 Sep 2025, so the rate they state comes from the
superseded schedule. Copying it is the single easiest way to poison this
dataset, and the annotator sees this panel a few hundred times.
"""

from harness.label.cli import _print_hints

AAR_META = {
    "transforms": ["strip_gstin"],
    "state": "West Bengal",
    "order_no": "44/WBAAR/2018-19 dated 13.03.19",
    "hsn_candidates": ["9608", "960810", "96089990"],
    "ruling_brief": "Classification of and rate of tax on tips and balls of ball point pens.",
    "ruling_url": "https://gstcouncil.gov.in/sites/default/files/AAR/x.pdf",
    "stale_rates_in_ruling": ["12", "18"],
}


def test_safe_hints_are_shown(capsys):
    _print_hints(AAR_META)
    out = capsys.readouterr().out
    assert "West Bengal" in out
    assert "9608" in out
    assert "ball point pens" in out


def test_stale_rates_carry_a_warning_not_a_bare_value(capsys):
    _print_hints(AAR_META)
    out = capsys.readouterr().out
    assert "must NOT be copied" in out
    assert "9/2025" in out


def test_abolished_slab_prompts_the_rate_changed_tag(capsys):
    _print_hints(AAR_META)
    out = capsys.readouterr().out
    # A ruling quoting 12% is by construction a rate-changed-2025 example.
    assert "rate-changed-2025" in out


def test_no_stale_warning_when_the_ruling_states_no_rates(capsys):
    _print_hints({"state": "Gujarat", "hsn_candidates": ["7311"]})
    out = capsys.readouterr().out
    assert "must NOT be copied" not in out
    assert "Gujarat" in out


def test_rates_without_twelve_do_not_mention_the_tag(capsys):
    _print_hints({"stale_rates_in_ruling": ["18"]})
    out = capsys.readouterr().out
    assert "must NOT be copied" in out
    assert "rate-changed-2025" not in out


def test_internal_fields_are_not_shown(capsys):
    _print_hints(AAR_META)
    assert "strip_gstin" not in capsys.readouterr().out


def test_empty_metadata_prints_nothing(capsys):
    _print_hints({})
    assert capsys.readouterr().out == ""


def test_openfoodfacts_hints_still_render(capsys):
    _print_hints({"categories": "Table salts, Groceries", "quantity": "1 kg", "labels": ""})
    out = capsys.readouterr().out
    assert "Table salts" in out
    assert "1 kg" in out
