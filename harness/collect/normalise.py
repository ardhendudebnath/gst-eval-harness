"""Text normalisation applied at collection time.

Implements the steps documented in data/DATA_LICENCE.md §3. Every transform
here is recorded per-example so the dataset can say exactly what was done to
the source text.
"""

from __future__ import annotations

import re
import unicodedata

MIN_LEN = 8
MAX_LEN = 12_000

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE_RE = re.compile(r"(?:\+91[\s-]?)?\b\d{10}\b|\b\d{3,5}[\s-]\d{6,8}\b")
_WS_RE = re.compile(r"\s+")

# Marketing furniture that carries no classification signal.
_FURNITURE_RE = re.compile(
    r"\b(?:buy\s+now|shop\s+now|free\s+delivery|free\s+shipping|cash\s+on\s+delivery|"
    r"best\s+seller|bestseller|limited\s+(?:time\s+)?offer|hurry|sale\s+ends|"
    r"lowest\s+price|deal\s+of\s+the\s+day|new\s+arrival|out\s+of\s+stock|"
    r"click\s+here|order\s+online)\b",
    re.I,
)

_RATING_RE = re.compile(r"[★☆⭐✩✪✫✬✭✮✯]+|\(\s*\d+(?:\.\d+)?\s*/\s*5\s*\)")

# Applicant-identifying detail in advance rulings (DATA_LICENCE.md §3.4).
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")
_APPLICANT_RE = re.compile(
    r"\b(?:M/s\.?|Messrs\.?)\s+[A-Z][\w&.,'\- ]{2,80}?(?=\s*(?:,|\.|having|is|has|the applicant|$))",
    re.I,
)


def _strip_emoji(text: str) -> str:
    return "".join(
        ch for ch in text if unicodedata.category(ch) not in {"So", "Cs"}
    )


def normalise(text: str, *, is_ruling: bool = False) -> tuple[str, list[str]]:
    """Normalise source text.

    Returns the cleaned text and the list of transforms that actually fired,
    so `collection_meta` can record what happened to this specific record.
    """
    applied: list[str] = []
    out = text

    nfkc = unicodedata.normalize("NFKC", out)
    if nfkc != out:
        applied.append("nfkc")
        out = nfkc

    if is_ruling:
        for name, pattern in (("gstin", _GSTIN_RE), ("applicant", _APPLICANT_RE)):
            out, n = pattern.subn(" ", out)
            if n:
                applied.append(f"strip_{name}")

    for name, pattern in (
        ("url", _URL_RE),
        ("email", _EMAIL_RE),
        ("phone", _PHONE_RE),
        ("furniture", _FURNITURE_RE),
        ("rating", _RATING_RE),
    ):
        out, n = pattern.subn(" ", out)
        if n:
            applied.append(f"strip_{name}")

    de_emoji = _strip_emoji(out)
    if de_emoji != out:
        applied.append("strip_emoji")
        out = de_emoji

    collapsed = _WS_RE.sub(" ", out).strip(" \t\n\r-–—,;·|")
    if collapsed != out:
        applied.append("collapse_ws")
    return collapsed, applied


def in_length_bounds(text: str) -> bool:
    return MIN_LEN <= len(text) <= MAX_LEN
