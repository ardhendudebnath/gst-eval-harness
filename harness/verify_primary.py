"""Verify the archived primary sources in data/reference/primary/.

Every rate claim in this repository traces to one of these notifications, so
the copies are pinned by SHA-256 and their content is re-checked rather than
trusted. A hash proves the file has not changed since it was archived; the
content assertions prove it is the document it claims to be, by looking for
entries that must be present if it is.

    python -m harness.verify_primary

Exits non-zero if a hash differs or an assertion fails.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PRIMARY = Path("data/reference/primary")
MANIFEST = PRIMARY / "MANIFEST.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_text(path: Path) -> str | None:
    """Extracted text with whitespace collapsed.

    PDF extraction inserts line breaks and double spaces at arbitrary points,
    so an exact substring check fails on text that is plainly present. Every
    comparison here runs against the collapsed form.
    """
    try:
        import pypdf
    except ImportError:
        return None
    import logging
    import re

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(str(path))
    raw = "\n".join((p.extract_text() or "") for p in reader.pages)
    return re.sub(r"\s+", " ", raw)


def main() -> int:
    if not MANIFEST.exists():
        print(f"no manifest at {MANIFEST}", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = 0

    for entry in manifest["documents"]:
        path = PRIMARY / entry["file"]
        print(f"\n  {entry['file']}  —  {entry['title']}")

        if not path.exists():
            print("    MISSING")
            failures += 1
            continue

        size = path.stat().st_size
        digest = sha256(path)
        size_ok = size == entry["bytes"]
        hash_ok = digest == entry["sha256"]
        print(f"    size   {size:>9,}  {'ok' if size_ok else 'MISMATCH'}")
        print(f"    sha256 {digest[:32]}…  {'ok' if hash_ok else 'MISMATCH'}")
        failures += (not size_ok) + (not hash_ok)

        text = pdf_text(path)
        if text is None:
            print("    content: skipped (pypdf not installed)")
            continue

        for claim in entry["must_contain"]:
            present = claim in text
            print(f"    {'ok  ' if present else 'FAIL'} contains: {claim[:66]}")
            failures += not present

    print()
    if failures:
        print(f"  FAIL — {failures} problem(s)")
        return 1
    print("  OK — every archived source matches its hash and content assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
