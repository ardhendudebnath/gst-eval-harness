"""Notification 19/2025, checked against the archived Gazette.

`AMENDED_2026` is transcribed from `data/reference/primary/19-2025-CTR.pdf`
because the amending prose is three sentences of legal drafting and a regex
over it would be more fragile than the table. Transcription is only safe if
something checks it, so this does: every heading, schedule and description
below is matched against the text of the archived document itself.

If these fail, either the transcription is wrong or the archived PDF changed.
Both are things you want to be told about loudly.
"""

from __future__ import annotations

import re

import pytest

from harness.collect.schedule_lookup import (
    AMENDED_2026,
    PRIMARY,
    SCHEDULE_SLAB,
    _text,
    lookup,
)

N19 = PRIMARY / "19-2025-CTR.pdf"

pytestmark = pytest.mark.skipif(
    not N19.exists(), reason="archived notification 19/2025 not present"
)


@pytest.fixture(scope="module")
def text():
    return re.sub(r"\s+", " ", _text(str(N19)))


def test_the_notification_is_the_one_we_think_it_is(text):
    assert "19/2025- Central Tax (Rate)" in text
    assert "31st December, 2025" in text
    assert "1 st day of February, 2026" in text or "1st day of February, 2026" in text


def test_schedule_vii_is_omitted_by_it(text):
    assert re.search(r"Schedule\s+VII\s*[–-]\s*14%.{0,60}?omitted", text, re.S)


def test_biris_go_to_schedule_ii(text):
    """The split that makes this the sharpest rate-changed case in the corpus:
    every other tobacco line went to 40%, biris went to 18%."""
    assert "Schedule II – 9%" in text or "Schedule II - 9%" in text
    assert "2403 19 21, 2403 19 29 Biris" in text
    assert AMENDED_2026["2403"][0] == (
        "2403 19 21, 2403 19 29", "II", "Biris"
    )
    assert SCHEDULE_SLAB["II"] == "18"


def test_the_rest_of_tobacco_goes_to_schedule_iii(text):
    assert "Schedule III – 20%" in text or "Schedule III - 20%" in text
    for heading in ("2106 90 20", "2401", "2402", "2404 11 00", "2404 19 00"):
        assert heading in text, f"{heading} not in the notification"
    assert SCHEDULE_SLAB["III"] == "40"


@pytest.mark.parametrize("heading,sub,schedule", [
    ("2106", "2106 90 20", "III"),
    ("2401", "", "III"),
    ("2402", "", "III"),
    ("2404", "2404 11 00", "III"),
    ("2404", "2404 19 00", "III"),
    ("2403", "2403 19 21, 2403 19 29", "II"),
])
def test_every_transcribed_row_appears_in_the_document(heading, sub, schedule, text):
    rows = AMENDED_2026[heading]
    assert any(s == sub and sc == schedule for s, sc, _ in rows), (
        f"{heading}/{sub} -> {schedule} is not in AMENDED_2026"
    )
    if sub:
        assert sub in text


def test_no_transcribed_row_invents_a_heading(text):
    """Nothing in the table may be absent from the notification."""
    for heading, rows in AMENDED_2026.items():
        for sub, _, _ in rows:
            token = (sub or heading).split()[0].split("(")[0]
            assert token in text, f"{token} is not in notification 19/2025"


# --- what the lookup now reports -----------------------------------------

def test_a_relocated_heading_no_longer_reports_no_entry():
    """Before this, 2402 read as having no current rated entry, because the
    lookup saw only Schedule VII in the un-amended 9/2025."""
    m = lookup("2402")
    assert m.slab == "40" and m.schedule == "III"
    assert not m.ambiguous


def test_the_biri_split_is_reported_as_a_real_choice():
    m = lookup("2403")
    assert m.ambiguous and m.slab is None
    assert {e.slab for e in m.entries} == {"18", "40"}


def test_two_entries_at_the_same_rate_are_not_ambiguous():
    """2404 has two sub-headings and both are 40%; which applies changes
    nothing about the rate, so the annotator has no choice to make."""
    m = lookup("2404")
    assert len(m.entries) == 2 and m.slab == "40" and not m.ambiguous


def test_an_omitted_schedule_vii_entry_is_never_offered():
    """Offering a rate that no longer exists is the exact error this project
    measures. None of these may come back as a live entry."""
    for heading in AMENDED_2026:
        m = lookup(heading)
        assert all(e.schedule != "VII" for e in m.entries)
        assert all(e.slab != "28" for e in m.entries)


def test_unrelated_headings_are_untouched():
    assert lookup("2523").slab == "18"
    assert lookup("6815").slab == "18"
