"""Rebuilding ruling excerpts at a different word cap.

The cap is a policy choice, not a property of the source, so changing it must
never require re-crawling: the PDF is already cached and the index metadata is
already in the record.
"""

from pathlib import Path

import pytest

from harness.collect.aar import CACHE, cached_pdf_for, reextract

RECORD = {
    "source": "aar",
    "source_id": "does-not-exist.pdf",
    "input": "The applicant manufactures widgets of assorted kinds and sizes.",
    "collected_at": "2026-09-03T12:00:00+00:00",
    "collection_meta": {
        "state": "Gujarat",
        "order_no": "GUJ/GAAR/R/2018/10",
        "ruling_url": "https://gstcouncil.gov.in/sites/default/files/AAR/does-not-exist.pdf",
        "hsn_candidates": ["7613"],
        "stale_rates_in_ruling": ["12"],
        "truncated": True,
    },
}


def test_missing_cached_pdf_returns_none():
    assert reextract(RECORD, 1200) is None


def test_missing_pdf_does_not_mutate_the_record():
    before = dict(RECORD["collection_meta"])
    reextract(RECORD, 1200)
    assert RECORD["collection_meta"] == before


def _a_cached_ruling():
    """A cached PDF that currently yields a usable excerpt, or None."""
    for pdf in sorted(CACHE.glob("*.pdf"))[:40]:
        rec = {
            "source": "aar",
            "source_id": pdf.name,
            "input": "placeholder",
            "collection_meta": {"state": "X", "hsn_candidates": [], "ruling_url": ""},
        }
        if reextract(rec, 300) is not None:
            return rec
    return None


def test_raising_the_cap_yields_a_longer_excerpt():
    pytest.importorskip("pypdf")
    rec = _a_cached_ruling()
    if rec is None:
        pytest.skip("no usable cached ruling available")

    short = reextract(rec, 300)
    long = reextract(rec, 1200)

    assert len(short["input"].split()) <= 300
    # Every ruling measured so far exceeds 300 words, so raising the cap must
    # produce strictly more text.
    assert len(long["input"].split()) > len(short["input"].split())
    assert long["input"].startswith(short["input"][:120])


def test_reextract_records_the_cap_and_truncation_flag():
    pytest.importorskip("pypdf")
    rec = _a_cached_ruling()
    if rec is None:
        pytest.skip("no usable cached ruling available")

    out = reextract(rec, 1200)
    assert out["collection_meta"]["max_words"] == 1200
    assert isinstance(out["collection_meta"]["truncated"], bool)


def test_index_metadata_survives_reextraction():
    pytest.importorskip("pypdf")
    rec = _a_cached_ruling()
    if rec is None:
        pytest.skip("no usable cached ruling available")

    rec["collection_meta"]["state"] = "Karnataka"
    rec["collection_meta"]["order_no"] = "KAR/ADRG/17/2018"
    out = reextract(rec, 900)
    # State, order number and the rest come from the index, not the PDF, so a
    # rebuild must carry them through untouched.
    assert out["collection_meta"]["state"] == "Karnataka"
    assert out["collection_meta"]["order_no"] == "KAR/ADRG/17/2018"
    assert out["source_id"] == rec["source_id"]


def test_cache_path_is_where_the_collector_writes():
    assert CACHE == Path("data/cache/aar")


def test_cached_pdf_for_resolves_from_source_id():
    assert cached_pdf_for(RECORD) == CACHE / "does-not-exist.pdf"


def test_cached_pdf_for_falls_back_to_the_ruling_url():
    rec = {"collection_meta": {"ruling_url": "https://x/sites/default/files/AAR/abc.pdf"}}
    assert cached_pdf_for(rec) == CACHE / "abc.pdf"


def test_absent_cache_is_distinguishable_from_rejection():
    # This is what stops `rescreen --reextract` deleting the whole pool on a
    # fresh clone, where data/cache/ is git-ignored and therefore empty.
    assert not cached_pdf_for(RECORD).exists()
    assert reextract(RECORD, 1200) is None
