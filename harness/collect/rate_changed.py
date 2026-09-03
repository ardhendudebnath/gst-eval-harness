"""Surface product listings that *may* belong to a family whose rate moved.

This is a search aid, not a classifier. It answers "is this worth the
annotator's attention while they fill the rate-changed-2025 slice?" and nothing
more. It never decides whether a rate actually moved, because that requires
establishing the heading and reading Notification 9/2025 — which is the
annotator's job under `data/guideline.md` §3, and is exactly the judgement this
benchmark exists to measure models against.

Two reasons the distinction is not pedantic:

  * A family moving does not mean an item moved. Many staple foods were already
    at 0% or 5% before the reform, so a match here is often a false positive.
  * Packaging conditionality (§4a) runs first and can change the answer for an
    individual listing regardless of family.

The families come from `data/reference/rate_changes_2025.md`, which cites the
official announcements and carries its own verification checklist.
"""

from __future__ import annotations

import re

#: Families announced as moving on 22 Sep 2025, mapped to listing vocabulary.
#: Keys are the family names used in the reference document.
RATE_CHANGED_FAMILIES: dict[str, tuple[str, ...]] = {
    # 18% -> 5%, personal and household care
    "hair oil": ("hair oil", "coconut oil", "amla oil", "hair care oil"),
    "shampoo": ("shampoo",),
    "toothpaste": ("toothpaste", "tooth paste", "tooth powder", "dentifrice", "dant manjan"),
    "toothbrush": ("toothbrush", "tooth brush"),
    "toilet soap": ("bathing soap", "bath soap", "toilet soap", "bathing bar", "soap bar"),
    "shaving cream": ("shaving cream", "shaving gel", "shave cream"),
    # 12% -> 5%, packaged foods and dairy
    "butter and ghee": ("butter", "ghee", "makhan"),
    "cheese": ("cheese", "dairy spread", "processed cheese"),
    "namkeen": ("namkeen", "bhujia", "mixture", "sev", "chivda", "farsan"),
    "sauces": ("sauce", "ketchup", "tomato puree"),
    "pasta and noodles": ("pasta", "noodle", "macaroni", "vermicelli", "spaghetti"),
    "chocolate": ("chocolate", "cocoa"),
    "coffee": ("coffee",),
    "cereal preparations": ("cornflake", "corn flake", "muesli", "breakfast cereal", "oats"),
    "biscuits": ("biscuit", "cookie", "cracker"),
}

#: Compiled once; word-boundary matching so "sev" does not fire inside
#: "several" and "oats" does not fire inside "coats".
_PATTERNS: dict[str, re.Pattern[str]] = {
    family: re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")s?\b", re.I
    )
    for family, terms in RATE_CHANGED_FAMILIES.items()
}


def candidate_families(text: str) -> list[str]:
    """Families this listing might belong to. Empty means "not a candidate"."""
    return [family for family, pat in _PATTERNS.items() if pat.search(text)]


def is_candidate(text: str) -> bool:
    return bool(candidate_families(text))


def record_candidate_families(record: dict) -> list[str]:
    """As `candidate_families`, reading the listing text and its catalogue category.

    The category matters for the same reason it matters in scope screening: a
    listing reading "Amul, 500 g" names no family, while its category does.
    """
    meta = record.get("collection_meta", {})
    haystack = " ".join(
        [
            record.get("input", ""),
            str(meta.get("categories") or ""),
            str(meta.get("labels") or ""),
        ]
    )
    return candidate_families(haystack)
