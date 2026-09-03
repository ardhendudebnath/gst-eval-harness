"""Collect real Indian packaged-food product records from Open Food Facts.

Open Food Facts is ODbL-licensed and redistributable with attribution, and its
India subset is large, genuinely messy, and dense in exactly the goods where GST
classification is subtle: staples that flip between 0% and 5% on whether they
are pre-packaged and labelled.

Stdlib-only (urllib) so collection works on a fresh clone with no installs.

    python -m harness.collect.openfoodfacts --pages 12 --out data/raw/off.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from harness.collect.normalise import in_length_bounds, normalise
from harness.schema import out_of_scope_term

API = "https://world.openfoodfacts.org/api/v2/search"
UA = "gst-eval-harness/0.1 (research benchmark; +https://github.com/)"

FIELDS = ",".join(
    [
        "code",
        "product_name",
        "brands",
        "quantity",
        "packaging",
        "categories",
        "labels",
        "ingredients_text",
    ]
)

# A quantity is only kept if it carries a unit. Bare "75" is catalogue noise.
_QTY_RE = re.compile(
    r"\d\s*(?:g|gm|gms|gram|kg|mg|ml|l|ltr|lt|litre|liter|cl|oz|lb|"
    r"pc|pcs|piece|pieces|pack|packs|n|no|nos|dozen)\b",
    re.I,
)

# Container words only. The packaging field also carries materials ("Plastic")
# and, in dirty records, country names ("India") — neither belongs in a listing
# description. Container words are kept because they are real signal for the
# pre-packaged-and-labelled test in guideline.md §4a.
_PACKAGING_WORDS: frozenset[str] = frozenset(
    {
        "pouch",
        "packet",
        "sachet",
        "bottle",
        "can",
        "carton",
        "box",
        "jar",
        "tin",
        "bag",
        "tube",
        "tetra pak",
        "tetrapak",
        "wrapper",
        "blister",
    }
)

_DEDUPE_RE = re.compile(r"[^a-z0-9]+")


def _get(url: str, *, retries: int = 6) -> dict:
    """GET with backoff.

    Open Food Facts is volunteer-run and returns 503 under load often enough
    that a short backoff loses whole runs. Overload responses get a longer,
    jittered wait than ordinary transport errors.
    """
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            wait = min(60.0, 5.0 * 2**attempt) + random.uniform(0, 3)
            print(f"  HTTP {exc.code}; retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2**attempt + random.random())
    raise RuntimeError(f"giving up on {url}: {last}")


def _clean_quantity(raw: str | None) -> str:
    q = (raw or "").strip()
    return q if q and _QTY_RE.search(q) else ""


def _clean_packaging(raw: str | None) -> str:
    for part in (raw or "").split(","):
        part = part.strip().lower().removeprefix("en:").replace("-", " ")
        if part in _PACKAGING_WORDS:
            return part
    return ""


def _describe(p: dict) -> str:
    """Rebuild a listing-style description from the catalogue fields.

    Assembles only facts already present in the record — brand, product name,
    declared quantity, container. Nothing is invented or paraphrased; this is
    concatenation, which is what keeps the corpus non-synthetic.
    """
    name = (p.get("product_name") or "").strip()
    if not name:
        return ""

    brand = (p.get("brands") or "").split(",")[0].strip()
    # Avoid "Tata Tata Salt": many catalogue names already carry the brand.
    head = f"{brand} {name}" if brand and brand.lower() not in name.lower() else name

    parts = [head]
    if qty := _clean_quantity(p.get("quantity")):
        parts.append(qty)
    if pack := _clean_packaging(p.get("packaging")):
        parts.append(pack)
    return ", ".join(parts)


def _out_of_scope(text: str, product: dict) -> str | None:
    """Screen the description *and* the catalogue metadata.

    A listing reading "Thums up, 250 ml" never says "carbonated" — that word
    only appears in the category field. Screening the description alone lets
    the whole aerated-beverage family into the pool.
    """
    haystack = " ".join(
        [
            text,
            str(product.get("categories") or ""),
            str(product.get("labels") or ""),
            str(product.get("product_name") or ""),
        ]
    )
    return out_of_scope_term(haystack)


def _dedupe_key(text: str) -> str:
    return _DEDUPE_RE.sub("", text.lower())


def collect(pages: int, page_size: int, out_path: Path) -> int:
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                seen_ids.add(rec["source_id"])
                seen_keys.add(_dedupe_key(rec["input"]))
        print(f"resuming — {len(seen_ids)} records already collected", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written = 0
    dropped = {"no_name": 0, "out_of_scope": 0, "length": 0, "duplicate": 0}
    families: Counter[str] = Counter()

    with out_path.open("a", encoding="utf-8") as fh:
        for page in range(1, pages + 1):
            qs = urllib.parse.urlencode(
                {
                    "countries_tags_en": "india",
                    "fields": FIELDS,
                    "page_size": page_size,
                    "page": page,
                }
            )
            try:
                payload = _get(f"{API}?{qs}")
            except (RuntimeError, urllib.error.HTTPError) as exc:
                # Everything written so far is already on disk and the run is
                # resumable, so a dead upstream ends the run rather than
                # discarding it. Sustained load makes the API answer 503 and
                # eventually 401, so this path is normal, not exceptional.
                print(f"page {page}: {exc}\n  stopping; re-run to resume", file=sys.stderr)
                break

            products = payload.get("products", [])
            if not products:
                print(f"page {page}: empty, stopping", file=sys.stderr)
                break

            kept = 0
            for p in products:
                code = str(p.get("code") or "")
                if not code or code in seen_ids:
                    continue

                raw = _describe(p)
                if not raw:
                    dropped["no_name"] += 1
                    continue

                text, applied = normalise(raw)
                if not in_length_bounds(text):
                    dropped["length"] += 1
                    continue
                if term := _out_of_scope(text, p):
                    dropped["out_of_scope"] += 1
                    families[term] += 1
                    continue

                key = _dedupe_key(text)
                if key in seen_keys:
                    dropped["duplicate"] += 1
                    continue

                seen_ids.add(code)
                seen_keys.add(key)
                fh.write(
                    json.dumps(
                        {
                            "source": "off",
                            "source_id": code,
                            "input": text,
                            "collected_at": now,
                            "collection_meta": {
                                "transforms": applied,
                                "categories": p.get("categories") or "",
                                "labels": p.get("labels") or "",
                                "quantity": p.get("quantity") or "",
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                kept += 1
                written += 1

            print(f"page {page}/{pages}: kept {kept}/{len(products)}", file=sys.stderr)
            # Be a good citizen of a volunteer-run API. At 1s/page it starts
            # answering 503 within a few pages; 3s runs cleanly.
            time.sleep(3.0)

    print(f"\ndropped: {dropped}", file=sys.stderr)
    if families:
        print(f"out-of-scope families: {dict(families.most_common())}", file=sys.stderr)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=12)
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("data/raw/off.jsonl"))
    args = ap.parse_args()

    n = collect(args.pages, args.page_size, args.out)
    print(f"wrote {n} new records to {args.out}", file=sys.stderr)
    print(
        "Contains information from Open Food Facts, made available under ODbL 1.0.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
