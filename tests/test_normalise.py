from harness.collect.normalise import in_length_bounds, normalise


def test_collapses_whitespace_and_trims():
    out, applied = normalise("  Tata   Salt\n\n Iodised  ")
    assert out == "Tata Salt Iodised"
    assert "collapse_ws" in applied


def test_strips_marketing_furniture():
    out, applied = normalise("Amul Butter 500g - BUY NOW! Free Delivery")
    assert "buy now" not in out.lower()
    assert "free delivery" not in out.lower()
    assert "Amul Butter 500g" in out
    assert "strip_furniture" in applied


def test_strips_urls_emails_and_phones():
    out, applied = normalise(
        "Parle-G 800g https://example.com contact seller@example.com 9876543210"
    )
    assert "example.com" not in out
    assert "9876543210" not in out
    assert "Parle-G 800g" in out
    assert {"strip_url", "strip_email", "strip_phone"} <= set(applied)


def test_strips_rating_glyphs_and_emoji():
    out, applied = normalise("Maggi Noodles 70g ★★★★☆ (4.2/5) 🔥🔥")
    assert "★" not in out and "🔥" not in out and "4.2/5" not in out
    assert "Maggi Noodles 70g" in out


def test_ruling_mode_strips_applicant_and_gstin():
    # ABCDE1234F is the standard placeholder PAN in Indian tax documentation,
    # so this GSTIN is recognisably synthetic rather than someone's real one.
    # 15 characters: 2 state digits + 10-char PAN + entity digit + Z + checksum.
    text = "M/s Acme Foods Private Limited, having GSTIN 29ABCDE1234F1Z5, supplies atta."
    out, applied = normalise(text, is_ruling=True)
    assert "Acme Foods" not in out
    assert "29ABCDE1234F1Z5" not in out
    assert "supplies atta" in out
    assert "strip_applicant" in applied and "strip_gstin" in applied


def test_applicant_not_stripped_outside_ruling_mode():
    out, applied = normalise("M/s Acme Foods atta 5 kg")
    assert "Acme Foods" in out
    assert "strip_applicant" not in applied


def test_reports_only_transforms_that_fired():
    _, applied = normalise("Tata Salt 1 kg pouch")
    assert applied == []


def test_length_bounds():
    assert not in_length_bounds("short")
    assert in_length_bounds("Tata Salt 1 kg pouch")
    assert not in_length_bounds("x" * 12_001)
