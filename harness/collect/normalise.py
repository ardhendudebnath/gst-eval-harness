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
#
# Ruling PDFs are frequently OCR'd, and the OCR mangles exactly these tokens:
# a real GSTIN came back as "24ABCDE1234FlZ5" (letter l for digit 1), which the
# strict 15-character GSTIN grammar does not match. Matching the shape instead
# — two digits then thirteen alphanumerics — survives that damage. Over-matching
# here is harmless; leaking a taxpayer identifier is not.
_GSTIN_RE = re.compile(r"\b\d{2}[A-Za-z0-9]{13}\b")

#: "M/s" as OCR actually renders it. Scanned ruling PDFs produce "M / s",
#: "M /s" and "M/ s", and a pattern anchored on the tight form matches none of
#: them — which is how "[redacted], 16, Anand Colony,
#: Rampura" survived every party pattern and reached the published file.
#:
#: **The slash is required.** An earlier version admitted a bare "Ms", and the
#: patterns that use this fragment carry re.I, so "MS" matched — and MS is mild
#: steel. "The applicant manufactures MS Rod, MS Flat and MS Bracket of heading
#: 7214" was redacted down to "The applicant manufactures", destroying the
#: goods description that is the entire content of the example. MS Rod, MS
#: Flat, MS Bracket, MS Square rod and MS Dummy Coin all appear in this corpus
#: as goods.
#:
#: Nothing is lost by requiring the slash. The honorific "Ms. Sharma" is
#: matched by _PERSON_NAME_RE, which is deliberately case-sensitive and so
#: never sees "MS"; and a company written "Ms Acme" without a slash is not a
#: form these documents use.
#:
#: The (?!No) guard stays because OCR splits "M/s" in ways that can still reach
#: "G.O. Ms No. 110" and "Notification Ms. No. rr(2)/crR/...", which are
#: statutory citations, not parties.
_MS = r"M\s*/\s*s\.?\s*(?!No\b|No\.)"

# Permanent Account Number: five letters, four digits, one letter. Found in the
# corpus as "having PAN-ABCDE1234F and registered office at ...", which nothing
# here matched. A PAN identifies a taxpayer as directly as a GSTIN does, and
# this dataset is published, so the keyword form is stripped as well as the
# bare shape — OCR damage to a labelled PAN still leaves the label.
#
# The keyword form must still see a PAN-shaped token: exactly ten alphanumerics
# containing a digit. Accepting any 8-12 character word after "PAN" would strip
# "pan preparations" and "pan masala" — goods this dataset exists to classify.
_PAN_RE = re.compile(
    r"\bPAN\s*(?:No\.?|Number)?\s*[-:]?\s*"
    r"(?=[A-Za-z0-9]{10}\b)(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{10}\b"
    r"|\b[A-Za-z]{5}\d{4}[A-Za-z]\b"
)

# "registered office at Plot No.418, Kadodara" — no street-type word, so
# _STREET_ADDR_RE never fired. Anchored on the phrase instead of the shape.
#
# Stopping at any period truncates the match to "registered office at Plot No"
# and leaves ".418, Kadodara, Navsari" in the text, because Indian addresses are
# full of "No." and "Plot No.". A period only ends the address when it is not
# part of a number.
_REGISTERED_OFFICE_RE = re.compile(
    r"\b(?:registered|corporate|head|branch)\s+office\s*"
    r"(?:is\s+)?(?:at|in|situated\s+at|located\s+at)?\s*"
    r"(?:[^.]|\.(?=\s*\d)){0,160}",
    re.I,
)

# Third parties named in the reasoning — "other player in similar line, M/s
# Zenith Boilers Limited appears to have been clearing". _APPLICANT_RE terminates on
# punctuation or a small set of verbs, and prose like this continues past all
# of them. A company suffix is the reliable end of a company name.
_COMPANY_RE = re.compile(
    rf"\b(?:{_MS}|Messrs\.?\s*)[A-Z][\w&.'\- ]{{2,60}}?"
    # Compound forms first. Alternation is leftmost-match, and the quantifier
    # above is lazy, so listing "Private" before "Private Limited" ends the
    # match at "Private" and strands "Limited" in the text.
    r"(?:Private\s+Limited|Pvt\.?\s*Ltd\.?|Public\s+Limited"
    r"|Limited|Ltd\.?|Private|Pvt\.?|LLP|Industries|Enterprises?|Corporation"
    r"|Corp\.?|Company|Traders?|Mills|Works|Agencies|Associates)\b"
    # A name can carry a suffix word in the middle -- "Beta Traders Pvt Ltd."
    # ends the lazy match at "Traders" and strands "Pvt Ltd.". Trailing
    # corporate suffixes are absorbed. Only suffixes, never arbitrary
    # capitalised words, so this cannot run on into the sentence after it.
    r"(?:\s*(?:Pvt\.?|Ltd\.?|Limited|Private|LLP|Inc\.?|Co\.?)\b)*",
    re.I,
)

# The general shape, for names with no recognisable suffix: "[redacted]
# of Howrah" is a manufacturer named in the reasoning, and no suffix list would
# have caught it. A company name is the run of capitalised tokens after M/s,
# ending where ordinary lowercase prose resumes. Capped at six tokens so a
# sentence that continues in title case cannot be swallowed whole.
#
# "M/s" is required — a bare capitalised run is most of the notification's own
# goods vocabulary, and matching that would gut the dataset.
# The (?!No) guard is the same one _PERSON_NAME_RE carries, and for the same
# reason: "M/?s" also matches the "Ms" in "G.O.Ms No. 110, Revenue (CT-II)
# Department" and in "Notification Ms. No. ...", which are statutory citations,
# not parties. Without it this pattern deletes the legal text it sits next to.
#
# Requiring whitespace *after* each token strands the last one before
# punctuation -- "M/s Acme Foods Private Limited," would strip through
# "Private" and leave "Limited,". Tokens are joined by single spaces instead,
# so the run ends naturally at a comma, a period, or the first lowercase word.
_MS_NAME_RE = re.compile(
    rf"\b{_MS}[A-Z][\w.&'\-]*(?:\s+[A-Z][\w.&'\-]*){{0,5}}"
)

# Terminates on punctuation including brackets, because applicant names are
# routinely followed by "(for short-'applicant')" rather than a comma.
_APPLICANT_RE = re.compile(
    rf"\b(?:{_MS}|Messrs\.?\s*)[A-Z][\w&.'\- ]{{2,80}}?"
    r"(?=\s*(?:[,.()]|having\b|is\b|has\b|the applicant\b|$))",
    re.I,
)

# Several authorities (West Bengal most consistently) open a ruling with a
# labelled table rather than prose, so the applicant is never prefixed "M/s":
#
#     Name of the applicant  Eastern Housing Development ...  Address  4/2B, Example
#     Street, Kolkata- 700001  GSTIN  ...  Case Number 07 of 2019  ARN AD19...
#
# Each field is stripped by looking ahead to the next field label.
_NEXT_FIELD = (
    r"(?=\s*(?:Address\b|GSTIN\b|Case\s+No|ARN\b|Date\s+of\b|Order\s+(?:number|no)\b"
    r"|Applicant|Present\s+for\b|\d+\.\s|$))"
)
_APPLICANT_FIELD_RE = re.compile(
    r"\bName\s+of\s+the\s+[Aa]pplicant\s*:?\s*.{0,140}?" + _NEXT_FIELD, re.I | re.S
)
_ADDRESS_FIELD_RE = re.compile(
    r"\bAddress\s*:?\s*.{0,220}?" + _NEXT_FIELD, re.I | re.S
)
# Application Reference Number, e.g. AD190101000001A.
_ARN_RE = re.compile(r"\bAD\d{9,}[A-Z\d]*\b", re.I)
# Named representatives who appeared, e.g. "heard Amit Agarwal, Dy. General Manager".
_REPRESENTATIVE_RE = re.compile(
    r"(?:Applicant.{0,3}s\s+representative\s+heard|Present\s+for\s+the\s+applicant)"
    r"\s*:?\s*.{0,140}?(?=\s*(?:\d+\.\s|$))",
    re.I | re.S,
)
# Trailing street address ending in a PIN code.
_PINCODE_ADDR_RE = re.compile(r"[^.]{0,120}?\b\d{6}\b|\b\d{3}\s?\d{3}\b(?=\s*[.,])")

# Honorific-prefixed personal names. These are not only representatives: sole
# proprietors are named as individuals ("Mr. <name>, Prop. of ..."), and
# signature blocks carry the adjudicating members' names.
#
# The (?!No\.) guard is load-bearing. "G.O.Ms No. 110, Revenue (CT-II)
# Department" is a Telangana Government Order citation — legitimate legal text
# that a bare honorific pattern would silently destroy.
_PERSON_NAME_RE = re.compile(
    r"\b(?:Sri|Shri|Smt|Mr|Ms|Mrs|Dr)\.?\s+"
    r"(?!No\.)"
    r"[A-Z][\w.\-]{1,24}(?:\s+[A-Z][\w.\-]{1,24}){0,3}"
)

# The proprietor's surname is repeated without the honorific, so the
# honorific pattern alone leaves it behind: "Mr. <full name>, Prop.of .<surname>
# (hereinafter called as .<surname> or Applicant)".
_PROPRIETOR_RE = re.compile(
    r"\b[Pp]rop(?:rietor)?\.?\s*(?:of|:)?\s*\.?\s*"
    r"[A-Z][\w.\-]{1,30}(?:\s+[A-Z][\w.\-]{1,30}){0,2}"
)
_ALIAS_RE = re.compile(
    r"\b(?:herein\s*after|hereinafter)\s+(?:called|referred)\s+(?:as|to\s+as)\s*\.?\s*"
    r"[A-Z][\w.\-]{1,30}"
)

# A name identified by the role that follows it, with no honorific to key on.
# OCR is why this is needed: one advocate's name came through as "Srlnivasa
# Rao, Advocate" — the honorific "Sri" was merged into the given name and
# corrupted, so nothing marks the start of the name except the role after it.
_ROLE_NAME_RE = re.compile(
    r"\b[A-Z][\w.\-]{1,24}(?:\s+[A-Z][\w.\-]{1,24}){0,3}"
    r"(?=\s*,\s*(?:Advocates?|Chartered\s+Accountants?|C\.?A\.?\b|F\.?C\.?A\.?\b"
    r"|Consultants?|Tax\s+Consultants?|Authoris(?:ed)?\s+Representative"
    r"|Authoriz(?:ed)?\s+Representative|Prop\b))"
)

# "doing business at <address>" and "(Prop. : ), No. 18-100, <street>, <town>".
_BUSINESS_ADDR_RE = re.compile(
    r"\bdoing\s+business\s+at\b[^.]{0,160}", re.I
)
#
# "No." is optional: the address in "[redacted], 16,
# Anand Colony, Rampura" is introduced by a bare number, and requiring the
# prefix left it in the published file after the company name was removed.
#
# The street word must be preceded by a capitalised place name. Without that,
# a bare "Block" or "Cross" matches ordinary prose — "8471, computers and
# Block diagram" — and this pattern is greedy enough to take the sentence
# with it.
_STREET_ADDR_RE = re.compile(
    r"\b(?:No\.\s*)?\d[\w\-/]*\s*,[^.]{0,120}?"
    r"[A-Z][\w]+\s+"
    r"(?:Road|Street|Nagar|Lane|Colony|Layout|Cross|Block|Marg|Sarani)\b"
    r"[^.]{0,60}"
)

# Procedural furniture in rulings — the exact analogue of "Buy Now / Free
# Delivery" in a product listing, and stripped for the same reason. It carries
# no classification signal, and leaving it in would pad every input by a few
# hundred tokens, inflating the cost-per-correct-answer metric this benchmark
# reports. Each pattern is tightly anchored so it cannot eat goods text.
_RULING_FURNITURE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("page_marker", re.compile(r"\bPage\s+\d+\s+of\s+\d+\b", re.I)),
    (
        "appeal_notice",
        re.compile(
            r"(?:Note\s*:\s*)?Any\s+appeal\s+against\s+(?:the|this)\s+[Aa]dvance\s+"
            r"[Rr]uling.{0,400}?(?:is\s+communicated|communicated)\s*\.?",
            re.I | re.S,
        ),
    ),
    (
        "outset_recital",
        re.compile(
            r"At\s+the\s+outset,?\s+we\s+would\s+like\s+to\s+make\s+it\s+clear"
            r".{0,400}?(?:\bare\s+the\s+same\b|\bpari\s*materia\b|\.)",
            re.I | re.S,
        ),
    ),
    (
        "admissibility_recital",
        re.compile(
            r"Advance\s+ruling\s+is\s+admissible\s+on\s+.{0,120}?"
            r"section\s*97\s*\(\s*2\s*\)[^.]{0,60}\.",
            re.I | re.S,
        ),
    ),
    (
        "pending_declaration",
        re.compile(
            r"The\s+[Aa]pplicant\s+declares\s+th\s?at\s+the\s+issue\s+raised"
            r".{0,300}?admissibility\s+of\s+the\s+[Aa]pplication\s*\.",
            re.I | re.S,
        ),
    ),
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
        # Order matters: the labelled-table fields carry their own terminators,
        # so they are stripped before the looser prose and PIN-code patterns
        # get a chance to eat across a field boundary.
        for name, pattern in (
            ("applicant_field", _APPLICANT_FIELD_RE),
            ("address_field", _ADDRESS_FIELD_RE),
            ("representative", _REPRESENTATIVE_RE),
            ("gstin", _GSTIN_RE),
            ("pan", _PAN_RE),
            ("arn", _ARN_RE),
            ("registered_office", _REGISTERED_OFFICE_RE),
            # Before the looser applicant pattern, which would otherwise stop
            # short and leave the company suffix stranded.
            ("company", _COMPANY_RE),
            ("applicant", _APPLICANT_RE),
            # Last, so the tighter patterns above claim what they can first.
            ("ms_name", _MS_NAME_RE),
            ("person_name", _PERSON_NAME_RE),
            ("role_name", _ROLE_NAME_RE),
            ("proprietor", _PROPRIETOR_RE),
            ("alias", _ALIAS_RE),
            ("business_address", _BUSINESS_ADDR_RE),
            ("street_address", _STREET_ADDR_RE),
            ("address", _PINCODE_ADDR_RE),
            *_RULING_FURNITURE,
        ):
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
