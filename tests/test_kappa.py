import pytest

from harness.calibration.kappa import cohens_kappa, interpret


def test_perfect_agreement_with_two_labels():
    a = ["5", "18", "5", "0"]
    r = cohens_kappa(a, list(a))
    assert r.observed == 1.0
    assert r.kappa == pytest.approx(1.0)


def test_total_disagreement_is_negative():
    r = cohens_kappa(["5", "18", "5", "18"], ["18", "5", "18", "5"])
    assert r.observed == 0.0
    assert r.kappa < 0


def test_known_worked_example():
    # 2x2: both raters yes 20/no 30 style table with 10 off-diagonal.
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["n"] * 20 + ["y"] * 5
    r = cohens_kappa(a, b)
    assert r.observed == pytest.approx(0.80)
    assert r.expected == pytest.approx(0.50)
    assert r.kappa == pytest.approx(0.60)


def test_chance_agreement_gives_kappa_near_zero():
    a = ["5"] * 50 + ["18"] * 50
    b = (["5"] * 25 + ["18"] * 25) * 2
    r = cohens_kappa(a, b)
    assert r.kappa == pytest.approx(0.0, abs=1e-9)


def test_single_label_throughout_is_not_a_zero_division():
    r = cohens_kappa(["5"] * 10, ["5"] * 10)
    assert r.kappa == 1.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="length mismatch"):
        cohens_kappa(["5"], ["5", "18"])


def test_empty_raises():
    with pytest.raises(ValueError, match="no paired labels"):
        cohens_kappa([], [])


@pytest.mark.parametrize(
    "k,expected_word",
    [(0.10, "Unusable"), (0.50, "Moderate"), (0.70, "Substantial"), (0.90, "Strong")],
)
def test_interpretation_bands(k, expected_word):
    assert expected_word in interpret(k)


def test_matrix_renders_all_labels():
    r = cohens_kappa(["5", "18", "0"], ["5", "0", "0"])
    out = r.render_matrix()
    for label in ("0", "5", "18"):
        assert label in out
