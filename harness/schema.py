"""Golden-set schema, and a validator with no third-party dependencies.

Deliberately stdlib-only: `make validate` has to work on a fresh clone before
anyone has run `pip install`. A dataset you cannot check is a dataset you cannot
trust.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# --------------------------------------------------------------------------
# Label space. See data/reference/rate_schedule.md.
# --------------------------------------------------------------------------

#: Combined GST rates available under Notification 9/2025 (as amended by
#: 19/2025) plus the 10/2025 exemptions. Verified against the Gazette text.
VALID_SLABS: tuple[str, ...] = ("0", "0.25", "1.5", "3", "5", "18", "40")

#: Sentinel for "the description does not support any slab".
UNANSWERABLE = "UNANSWERABLE"

#: Quarantine-only sentinel for "the model could not derive a slab it could
#: defend". Deliberately distinct from UNANSWERABLE, which is a positive
#: finding about the *description*; this is an admission about the *model*.
#: Conflating them would let model ignorance masquerade as a dataset label.
UNCERTAIN = "UNCERTAIN"

#: Slabs that no longer exist. A model emitting one is reciting a rate table
#: that has been superseded, which the harness scores separately as the
#: stale-slab rate.
#:
#:   12%  abolished 22 Sep 2025 — the 6% CGST schedule of Notification 1/2017
#:        has no successor in 9/2025.
#:   28%  abolished  1 Feb 2026 — Notification 19/2025-CT(Rate) omits
#:        "the Schedule VII – 14%, and the entries relating thereto".
#:        Tobacco and pan masala moved to Schedule III (40%), biris to
#:        Schedule II (18%).
#:
#: Both dates matter: a model can be stale by six months or by eighteen, and
#: the two are distinguishable in its output.
ABOLISHED_SLABS: frozenset[str] = frozenset({"12", "28"})

#: When each abolished slab ceased to exist, for reporting.
SLAB_ABOLISHED_ON: dict[str, str] = {"12": "2025-09-22", "28": "2026-02-01"}

DIFFICULTIES: frozenset[str] = frozenset(
    {"typical", "hard", "long_context", "adversarial", "out_of_scope"}
)

#: Target composition from guideline.md §8, as a share of the frozen set.
TARGET_STRATA: dict[str, float] = {
    "typical": 0.40,
    "hard": 0.25,
    "long_context": 0.15,
    "adversarial": 0.10,
    "out_of_scope": 0.10,
}

UNANSWERABLE_REASONS: frozenset[str] = frozenset(
    {
        "no-product-kind",
        "model-number-only",
        "rate-fact-absent",
        "packaging-indeterminate",
        "multi-good-no-dominant",
    }
)

SOURCES: frozenset[str] = frozenset({"off", "aar", "ogd", "gem"})

#: Who made the judgement. The plan permits model assistance for a first pass
#: only if every example is human-reviewed and the assistance is disclosed, so
#: provenance is a field rather than a convention.
LABELLERS: frozenset[str] = frozenset(
    {
        "human",           # labelled directly by the annotator
        "model-first-pass",  # model suggestion, NOT reviewed — quarantined
        "human-reviewed",  # model suggestion the annotator accepted or corrected
        "gazette-derived",  # a document lookup, no human judgement — see below
    }
)

#: Rows whose slab was read out of the hash-pinned notification rather than
#: judged, and which no human has confirmed.
#:
#: Admissible because nothing in them is recalled. The heading comes from the
#: authority's own operative ruling in the source document; the slab comes from
#: `schedule_lookup`, which reads the archived Gazette and refuses to resolve
#: any heading that appears in more than one schedule. A model's recollection
#: of Indian GST rates is the pre-2025 table — the exact error this benchmark
#: exists to measure — and none of it is used to produce these.
#:
#: What they are NOT is human judgement, and nothing may claim they are. They
#: cannot populate the `hard` or `adversarial` strata, which exist precisely
#: for calls a lookup cannot make, and any score computed over them belongs in
#: its own column beside the human-labelled one, never averaged into it.
DERIVED_LABELLERS: frozenset[str] = frozenset({"gazette-derived"})

#: Never permitted in the golden set. This is the guarantee that an unreviewed
#: model suggestion cannot become an example by accident — concatenating the
#: quarantine file into golden.jsonl fails validation loudly instead of
#: silently destroying the dataset's provenance claim.
QUARANTINED_LABELLERS: frozenset[str] = frozenset({"model-first-pass"})

_ID_RE = re.compile(r"^gst-\d{4}$")
_HSN4_RE = re.compile(r"^\d{4}$")
_REASON_RE = re.compile(r"reason=([a-z-]+)")

# Families excluded from the dataset (guideline §4d).
#
# Only one reason survives. Cement, aerated drinks, tobacco and pan masala were
# all excluded on the premise that they sat in Schedule VII awaiting a
# transitional decision; reading the Gazette settled every one of them, and all
# are now in scope. Each moved off the 28% slab that was itself abolished on
# 1 Feb 2026, which makes them the sharpest stale-slab probes in the corpus: a
# model reciting the old table answers 28%, an answer that is not merely wrong
# but names a rate that no longer exists.
#
# What remains is **alcoholic liquor for human consumption**, which is outside
# GST by constitutional exclusion and taxed under state excise. There is no
# slab to predict, so this exclusion is categorical rather than provisional —
# it is not the same kind of decision as the others and must not be lifted by
# analogy to them.
#
# Note for tobacco: a separate excise duty was introduced alongside the 40%
# rate. That is a different levy, not a GST slab, and does not affect the
# answer to "which slab applies" any more than customs duty would.
OUT_OF_SCOPE_TERMS: tuple[str, ...] = (
    "beer",
    "wine",
    "whisky",
    "whiskey",
    "whiskies",
    "vodka",
    "rum",
    "liquor",
    "alcoholic",
)

# Word-boundary matching, so "rumali roti" is not rejected for containing "rum".
#
# The trailing (?:e?s)? matters more than it looks: catalogue categories are
# written in the plural ("Cigarettes", "Beers"), and a bare \b anchor silently
# fails against every one of them.
_OUT_OF_SCOPE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in OUT_OF_SCOPE_TERMS) + r")(?:e?s)?\b",
    re.I,
)


def out_of_scope_term(text: str) -> str | None:
    """Return the out-of-scope family this text names, or None.

    The single authority for scope screening — used by the collectors to reject
    records before they enter the labelling pool, and by the validator as a
    backstop for anything that slipped through.
    """
    m = _OUT_OF_SCOPE_RE.search(text)
    return m.group(0).lower() if m else None


# --------------------------------------------------------------------------


@dataclass(slots=True)
class Example:
    """One labelled example. Field order mirrors the JSONL on disk."""

    id: str
    input: str
    slab: str
    hsn4: str | None
    answerable: bool
    justification: str
    difficulty: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    source_id: str = ""
    collected_at: str = ""
    labelled_at: str = ""
    labeller_notes: str = ""
    labelled_by: str = "human"
    deprecated_by: str | None = None
    collection_meta: dict[str, Any] = field(default_factory=dict)
    #: Only on quarantined rows: why the model suggested this, and how much it
    #: trusted each field. Dropped once a human reviews the row.
    model_notes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Example":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in obj.items() if k in known})

    def to_json(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "input": self.input,
            "slab": self.slab,
            "hsn4": self.hsn4,
            "answerable": self.answerable,
            "justification": self.justification,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "source": self.source,
            "source_id": self.source_id,
            "collected_at": self.collected_at,
            "labelled_at": self.labelled_at,
            "labeller_notes": self.labeller_notes,
            "labelled_by": self.labelled_by,
            "collection_meta": self.collection_meta,
        }
        if self.deprecated_by:
            out["deprecated_by"] = self.deprecated_by
        if self.model_notes:
            out["model_notes"] = self.model_notes
        return out

    @property
    def is_active(self) -> bool:
        """False once superseded by a corrected row (guideline §7.2)."""
        return self.deprecated_by is None

    @property
    def unanswerable_reason(self) -> str | None:
        m = _REASON_RE.search(self.labeller_notes or "")
        return m.group(1) if m else None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_example(ex: Example, *, quarantine: bool = False) -> list[str]:
    """Return a list of human-readable problems; empty means valid.

    `quarantine=True` validates a row in the model first-pass file, where an
    unreviewed model label is expected. In the golden set it is an error.
    """
    errs: list[str] = []

    if ex.labelled_by not in LABELLERS:
        errs.append(f"labelled_by {ex.labelled_by!r} not in {sorted(LABELLERS)}")
    elif not quarantine and ex.labelled_by in QUARANTINED_LABELLERS:
        errs.append(
            f"labelled_by is {ex.labelled_by!r}: an unreviewed model suggestion "
            "cannot be a golden example. Review it with "
            "`python -m harness.label.cli --review-first-pass`."
        )

    if not _ID_RE.match(ex.id):
        errs.append(f"id {ex.id!r} does not match 'gst-NNNN'")

    if not ex.input or not ex.input.strip():
        errs.append("input is empty")

    # --- slab ------------------------------------------------------------
    if ex.slab in ABOLISHED_SLABS:
        errs.append(
            f"slab {ex.slab!r} was abolished on {SLAB_ABOLISHED_ON[ex.slab]} and "
            "cannot be a gold label (see data/reference/rate_schedule.md)"
        )
    elif ex.slab == UNCERTAIN and not quarantine:
        errs.append(
            f"slab {UNCERTAIN!r} means the model could not derive one; it is "
            "only valid in the first-pass quarantine file, never in the golden set"
        )
    elif ex.slab not in (UNANSWERABLE, UNCERTAIN) and ex.slab not in VALID_SLABS:
        errs.append(
            f"slab {ex.slab!r} not in {VALID_SLABS} or {UNANSWERABLE!r}"
        )

    # A quarantined row that could not be derived is exempt from the coherence
    # checks below — there is no slab yet for anything to agree with.
    if quarantine and ex.slab == UNCERTAIN:
        return errs

    # --- answerable must agree with slab ---------------------------------
    if ex.answerable and ex.slab == UNANSWERABLE:
        errs.append("answerable=true but slab is UNANSWERABLE")
    if not ex.answerable and ex.slab != UNANSWERABLE:
        errs.append(f"answerable=false but slab is {ex.slab!r}")

    # --- unanswerable rows need a diagnosable reason ----------------------
    if not ex.answerable:
        reason = ex.unanswerable_reason
        if reason is None:
            errs.append(
                "unanswerable row must carry 'reason=<code>' in labeller_notes"
            )
        elif reason not in UNANSWERABLE_REASONS:
            errs.append(
                f"unknown unanswerable reason {reason!r}; "
                f"expected one of {sorted(UNANSWERABLE_REASONS)}"
            )
        if ex.difficulty not in ("out_of_scope", "hard"):
            errs.append(
                f"unanswerable row has difficulty {ex.difficulty!r}; "
                "expected 'out_of_scope' or 'hard'"
            )

    # --- hsn4 ------------------------------------------------------------
    if ex.hsn4 is not None and not _HSN4_RE.match(ex.hsn4):
        errs.append(f"hsn4 {ex.hsn4!r} is not a 4-digit heading")
    if ex.answerable and ex.hsn4 is None:
        errs.append("answerable row is missing hsn4")

    # --- metadata --------------------------------------------------------
    if ex.difficulty not in DIFFICULTIES:
        errs.append(
            f"difficulty {ex.difficulty!r} not in {sorted(DIFFICULTIES)}"
        )
    if ex.source and ex.source not in SOURCES:
        errs.append(f"source {ex.source!r} not in {sorted(SOURCES)}")
    if not ex.justification.strip():
        errs.append("justification is empty")

    # --- scope ------------------------------------------------------------
    if term := out_of_scope_term(ex.input):
        errs.append(
            f"input mentions out-of-scope family {term!r} "
            "(guideline.md §4d) — drop this example"
        )

    return errs


# --------------------------------------------------------------------------
# JSONL I/O
# --------------------------------------------------------------------------


def read_jsonl(path: str | Path) -> Iterator[Example]:
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                yield Example.from_json(json.loads(line))
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"{p}:{lineno}: {exc}") from exc


def append_jsonl(path: str | Path, examples: Iterable[Example]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("a", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex.to_json(), ensure_ascii=False) + "\n")
            n += 1
    return n


def next_id(existing: Iterable[Example]) -> str:
    highest = 0
    for ex in existing:
        if _ID_RE.match(ex.id):
            highest = max(highest, int(ex.id.split("-")[1]))
    return f"gst-{highest + 1:04d}"
