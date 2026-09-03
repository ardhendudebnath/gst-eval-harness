"""The archived notifications are the ground truth for every rate in the repo.

These tests check the manifest is well-formed and that the archive actually
matches it, so a corrupted or swapped PDF is caught rather than silently
changing what the dataset means.
"""

import json

import pytest

from harness.verify_primary import MANIFEST, PRIMARY, pdf_text, sha256


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("no archived primary sources")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_lists_the_three_notifications(manifest):
    files = {d["file"] for d in manifest["documents"]}
    assert files == {"09-2025-CTR.pdf", "10-2025-CTR.pdf", "19-2025-CTR.pdf"}


def test_every_archived_file_exists_and_matches_its_hash(manifest):
    for doc in manifest["documents"]:
        path = PRIMARY / doc["file"]
        assert path.exists(), f"{doc['file']} is missing"
        assert path.stat().st_size == doc["bytes"]
        assert sha256(path) == doc["sha256"]


def test_hashes_are_full_length_sha256(manifest):
    for doc in manifest["documents"]:
        assert len(doc["sha256"]) == 64
        int(doc["sha256"], 16)  # raises if not hex


def test_every_document_carries_content_assertions(manifest):
    # A hash proves the file has not changed; the assertions prove it is the
    # document it claims to be.
    for doc in manifest["documents"]:
        assert doc["must_contain"], f"{doc['file']} has no content assertions"


def test_provenance_is_recorded_honestly(manifest):
    # The copies are from a mirror because CBIC's TLS chain is incomplete.
    # That limitation must stay written down, not quietly dropped.
    assert "mirror" in manifest["provenance"].lower()
    assert manifest["retrieved"]


def test_archived_content_assertions_hold(manifest):
    pypdf = pytest.importorskip("pypdf")
    for doc in manifest["documents"]:
        reader = pypdf.PdfReader(str(PRIMARY / doc["file"]))
        assert len(reader.pages) == doc["pages"]
        text = pdf_text(PRIMARY / doc["file"])
        for claim in doc["must_contain"]:
            assert claim in text, f"{doc['file']} no longer contains {claim!r}"


def test_the_entry_behind_the_pen_tips_verification_is_present():
    # Schedule II serial 626 is what settled that pen parts are 18%, and with
    # it that the pen-tips example is not a rate-changed one. The "parts"
    # clause is the operative words: tips and balls are parts of a pen.
    pytest.importorskip("pypdf")
    path = PRIMARY / "09-2025-CTR.pdf"
    if not path.exists():
        pytest.skip("no archived primary sources")
    text = pdf_text(path)
    assert "9608" in text
    assert "parts (including caps and clips) of the foregoing articles" in text


def test_the_biri_split_is_present():
    # Schedule II 4A vs Schedule III 17 — the within-heading split that makes
    # tobacco worth having in scope.
    pytest.importorskip("pypdf")
    path = PRIMARY / "19-2025-CTR.pdf"
    if not path.exists():
        pytest.skip("no archived primary sources")
    text = pdf_text(path)
    assert "2403 19 21" in text
    assert "Biris" in text
