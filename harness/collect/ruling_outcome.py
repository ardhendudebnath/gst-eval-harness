"""Extract what the authority actually decided, from the operative ruling.

The excerpt an annotator labels deliberately stops before the findings, so the
input cannot contain the answer. But the annotator still has to establish the
heading, and the authority already did that work in the same document. Pulling
the operative ruling out of the cached PDF is reading an authoritative source,
not forming a judgement — `data/guideline.md` §2a already sanctions a ruling's
HSN as a research hint, because HSN is the Customs Tariff and GST 2.0 did not
touch it.

**What this does not give you.** The rate. Almost every ruling here predates
22 September 2025 and cites Notification 1/2017, which has been superseded —
one states the answer as "6% CGST + 6% SGST", a 12% slab that no longer exists.
The heading is durable; the rate is not, and must be re-derived from
Notification 9/2025.

**Extraction is unreliable and says so.** Advance rulings have no common
format. Measured over the collected corpus it finds the operative ruling in
roughly half of them, and many determinations are conditional ("Heading 3307 or
3401 depending upon their constituents") or negative ("would not be covered by
Sl. No. 192"). A returned outcome is a starting point to verify, never an
answer to copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from harness.collect.normalise import normalise

#: Headings that introduce the operative ruling. Spaced-out forms like
#: "R U L I N G" are common in these PDFs.
_OPERATIVE = re.compile(
    r"(?:R\s?U\s?L\s?I\s?N\s?G\b"
    r"|we\s+rule\s+as\s+under"
    r"|[Rr]uling\s+is\s+given\s+as\s+under"
    r"|[Tt]he\s+following\s+ruling\s+is\s+(?:passed|given)"
    r"|ANSWER\s*:)",
    re.I,
)

#: Text after the heading must look like a determination, not a stray mention.
#: Stems carry \w* rather than \b — "classifiab" followed by \b can never match
#: "classifiable", because \b needs a non-word character and the next letter is
#: "l". The same trap applies to "attract" against "attracts".
_DETERMINATION = re.compile(
    r"\b(?:classifiab\w*|classif(?:ied|ication)|fall\w*\s+under|covered\s+by"
    r"|merit\w*\s+classification|attract\w*|chargeable|taxable|liable\s+to\s+tax"
    r"|would\s+not\s+be)\b",
    re.I,
)

_HSN = re.compile(
    r"\b(?:HSN|HS\s+code|heading|chapter\s+heading|tariff\s+item|sub-?heading)"
    r"[^0-9\n]{0,25}(\d{4}(?:\s?\d{2}){0,2})",
    re.I,
)
#: The alternative in "Heading 3307 or 3401" carries no keyword of its own, and
#: a conditional determination naming two competing headings is exactly the
#: case worth capturing in full.
_HSN_ALT = re.compile(r"\b(?:or|and)\s+(\d{4}(?:\s?\d{2}){0,2})\b", re.I)
_RATE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")
#: "6% CGST + 6% SGST" states half the combined rate twice.
_SPLIT_RATE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%\s*CGST", re.I)

#: Rulings usually name a Schedule of Notification 1/2017 rather than a
#: percentage. The mapping is fixed by that notification, and it is what tells
#: an applicant's *argument* apart from the authority's *holding*: an applicant
#: who claimed 12% and was placed in Schedule III did not have a 12% rate.
_SCHEDULE = re.compile(r"Schedule\s*[-–—]?\s*(VII|VI|V|IV|III|II|I)\b", re.I)
OLD_SCHEDULE_RATES: dict[str, str] = {
    "I": "5",
    "II": "12",
    "III": "18",
    "IV": "28",
    "V": "3",
    "VI": "0.25",
}

#: Question-section shapes. Rulings restate the questions before answering, so
#: a passage full of "Whether ... ?" is usually what was asked, not what was
#: decided — unless an answer follows it, which is the common Q/Ans layout.
_QUESTION_SHAPE = re.compile(r"\bWhether\b[^?]{0,240}\?|question\s+as\s+to", re.I)
_ANSWER_MARKER = re.compile(r"\bAns(?:wer)?\b\s*[.:\-]|\bReply\b\s*[.:]", re.I)

MIN_TAIL_CHARS = 150
MAX_QUOTE_CHARS = 600

#: Only look in the closing part of the order. Without this the extractor
#: happily returns the *question* section ("(ii) whether it is classifiable
#: under chapter heading 4911?") or a mid-discussion aside ("we find it
#: imperative to refer to Heading 9503"), both of which read like
#: determinations and neither of which is one. Measured on the collected
#: corpus, adding this roughly doubled precision.
TAIL_FRACTION = 0.55


@dataclass(slots=True)
class Outcome:
    """What the authority determined, as stated. Verify before relying on it."""

    quote: str
    headings: list[str] = field(default_factory=list)
    rates_stated: list[str] = field(default_factory=list)
    combined_rate_hint: str | None = None
    conditional: bool = False
    looks_like_question: bool = False
    #: Schedule of Notification 1/2017 named in the operative ruling, and the
    #: pre-22-Sep-2025 combined rate it implies. This is the rate the authority
    #: actually held, as distinct from whatever the applicant argued for.
    schedule: str | None = None
    held_rate: str | None = None

    @property
    def is_conditional(self) -> bool:
        """True when the determination depends on facts, e.g. "3307 or 3401"."""
        return self.conditional or len(self.headings) > 1

    @property
    def confidence(self) -> str:
        """A word for the annotator, not a probability."""
        if self.looks_like_question:
            return "low — reads like the question, not the ruling"
        if self.is_conditional:
            return "conditional — the heading depends on facts"
        return "reads like a determination"


def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_operative_ruling(text: str) -> str | None:
    """The operative ruling passage, or None if it cannot be located.

    Searched from the end, because the operative ruling closes the order and
    the word "ruling" appears many times before it — in the application, the
    admissibility recital and the discussion.
    """
    floor = int(len(text) * TAIL_FRACTION)
    for match in reversed(list(_OPERATIVE.finditer(text))):
        if match.start() < floor:
            break  # matches are in order; everything earlier is too early
        tail = text[match.end() : match.end() + MAX_QUOTE_CHARS * 2]
        if len(tail.strip()) < MIN_TAIL_CHARS:
            continue
        if not _DETERMINATION.search(tail):
            continue
        # Redact before returning. This passage comes straight out of the PDF
        # and has not been through the collector's pipeline, so without this it
        # carries party detail the rest of the corpus strips — an operative
        # ruling names the applicant and quoted one live GSTIN verbatim.
        redacted, _ = normalise(_normalise_ws(tail), is_ruling=True)
        return redacted[:MAX_QUOTE_CHARS]
    return None


def extract_outcome(text: str) -> Outcome | None:
    """Parse the operative ruling into headings and stated rates."""
    quote = find_operative_ruling(text)
    if quote is None:
        return None

    headings: list[str] = []
    for pattern in (_HSN, _HSN_ALT):
        for m in pattern.finditer(quote):
            code = re.sub(r"\s+", "", m.group(1))[:8]
            if len(code) == 4 and code.startswith(("19", "20")):
                continue  # a statute year, not a heading
            if code not in headings:
                headings.append(code)

    rates = sorted({r for r in _RATE.findall(quote)}, key=float)

    # "6% CGST + 6% SGST" means a combined 12%.
    combined = None
    if split := _SPLIT_RATE.search(quote):
        half = float(split.group(1))
        combined = f"{half * 2:g}"

    conditional = bool(
        re.search(r"\bor\b.{0,40}\bdepend|depending\s+upon|whichever|as\s+the\s+case",
                  quote, re.I)
    )

    # A question restated is not a determination — unless an answer follows,
    # which is the common "Q.1 Whether ... ? Ans. The product ..." layout.
    looks_like_question = bool(
        _QUESTION_SHAPE.search(quote) and not _ANSWER_MARKER.search(quote)
    )

    # What the authority held, from the schedule it named or a rate it stated.
    schedule = held_rate = None
    if sched_m := _SCHEDULE.search(quote):
        schedule = sched_m.group(1).upper()
        held_rate = OLD_SCHEDULE_RATES.get(schedule)
    if held_rate is None:
        if combined:
            held_rate = combined
        elif len(rates) == 1:
            held_rate = rates[0]

    return Outcome(
        quote=quote,
        headings=headings,
        rates_stated=rates,
        combined_rate_hint=combined,
        conditional=conditional,
        looks_like_question=looks_like_question,
        schedule=schedule,
        held_rate=held_rate,
    )
