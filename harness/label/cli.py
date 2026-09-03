"""Interactive labelling tool for the golden set.

The cost of this project is tedium, so this exists to make 400 careful
judgements survivable: one keypress for the slab, live stratum progress so you
know what you still need, and an enforced break every 50 rows because fatigue
shows up as self-disagreement and self-disagreement is the ceiling on every
model score.

    python -m harness.label.cli                      # label the next unlabelled row
    python -m harness.label.cli --filter atta        # hunt for a specific stratum
    python -m harness.label.cli --relabel 50         # blind re-label for self-agreement

Nothing here calls a model. See guideline.md §7.5.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from harness.collect.rate_changed import record_candidate_families
from harness.schema import (
    SOURCES,
    TARGET_STRATA,
    UNANSWERABLE,
    UNCERTAIN,
    UNANSWERABLE_REASONS,
    Example,
    append_jsonl,
    next_id,
    read_jsonl,
    validate_example,
)

GOLDEN = Path("data/golden.jsonl")
RAW_DIR = Path("data/raw")
BATCH_SIZE = 50

#: 12% and 28% are deliberately absent — both are abolished and cannot be a
#: gold label, so the key that would enter one does not exist.
SLAB_KEYS: dict[str, str] = {
    "a": "0",
    "b": "0.25",
    "c": "1.5",
    "d": "3",
    "e": "5",
    "f": "18",
    "h": "40",
}

DIFFICULTY_KEYS: dict[str, str] = {
    "1": "typical",
    "2": "hard",
    "3": "long_context",
    "4": "adversarial",
    "5": "out_of_scope",
}

REASON_KEYS = {str(i): r for i, r in enumerate(sorted(UNANSWERABLE_REASONS), 1)}

RULE = "─" * 72


class Quit(Exception):
    """Raised to unwind out of a nested prompt and save."""


# --------------------------------------------------------------------------
# pool
# --------------------------------------------------------------------------


def load_pool() -> list[dict]:
    """Every collected raw record, in stable order."""
    pool: list[dict] = []
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pool.append(json.loads(line))
    return pool


def _ask(prompt: str, *, allow_empty: bool = False) -> str:
    while True:
        try:
            # Strip a leading BOM as well as whitespace: piping input on
            # Windows injects one, which otherwise makes the first keystroke of
            # a scripted session silently unmatchable.
            val = input(prompt).lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            raise Quit from None
        if val.lower() == ":q":
            raise Quit
        if val or allow_empty:
            return val


def _menu(prompt: str, keys: dict[str, str], *, extra: dict[str, str] | None = None) -> str:
    extra = extra or {}
    while True:
        val = _ask(prompt).lower()
        if val in keys:
            return keys[val]
        if val in extra:
            return extra[val]
        print(f"    ? expected one of {sorted(keys) + sorted(extra)}")


# --------------------------------------------------------------------------
# progress
# --------------------------------------------------------------------------


def show_progress(labelled: list[Example], target_total: int) -> None:
    active = [e for e in labelled if e.is_active]
    counts = Counter(e.difficulty for e in active)
    print(f"\n{RULE}")
    print(f"  {len(active)} / {target_total} labelled")
    bits = []
    for stratum, frac in TARGET_STRATA.items():
        want = round(frac * target_total)
        have = counts.get(stratum, 0)
        mark = "ok" if have >= want else f"need {want - have}"
        bits.append(f"{stratum}={have}/{want} ({mark})")
    print("  " + "  ".join(bits))
    changed = sum(1 for e in active if "rate-changed-2025" in e.tags)
    print(f"  rate-changed-2025: {changed}/60")
    print(RULE)


# --------------------------------------------------------------------------
# one example
# --------------------------------------------------------------------------


def present(record: dict, ex_id: str, index: int, batch_pos: int) -> None:
    print(f"\n{RULE}")
    print(f"  {ex_id}   #{index}   batch item {batch_pos}/{BATCH_SIZE}   source={record.get('source', '?')}")
    print(RULE)
    text = record["input"]
    if len(text) > 2000:
        print(f"  {text[:2000]}\n  … [{len(text) - 2000} more chars]")
    else:
        print(f"  {text}")
    print(RULE)
    _print_hints(record.get("collection_meta", {}), record)


#: Metadata that helps and metadata that misleads are presented differently on
#: purpose. `stale_rates_in_ruling` is the single biggest labelling hazard in
#: this dataset, so it never appears as a plain hint.
_SAFE_HINTS = (
    "categories",
    "quantity",
    "labels",
    "state",
    "order_no",
    "hsn_candidates",
    "ruling_brief",
    "ruling_url",
    "pdf_pages",
    "truncated",
)


def _ruling_outcome(record: dict):
    """The authority's own determination, read from the cached PDF.

    The excerpt stops before the findings so the input cannot contain the
    answer, but the annotator still has to establish the heading — and the
    authority did that work in the same document. Best-effort: it locates the
    operative passage in roughly 60% of rulings, and says how much to trust
    what it found.
    """
    if record.get("source") != "aar":
        return None
    try:
        from harness.collect.aar import cached_pdf_for, extract_pdf_text
        from harness.collect.ruling_outcome import extract_outcome
    except Exception:  # noqa: BLE001 - pypdf is an optional extra
        return None

    pdf = cached_pdf_for(record)
    if not pdf.exists():
        return None
    try:
        text, _ = extract_pdf_text(pdf.read_bytes())
        return extract_outcome(text)
    except Exception:  # noqa: BLE001 - a hint is never worth a crash
        return None


def _print_hints(meta: dict, record: dict | None = None) -> None:
    record = record or {"collection_meta": meta}
    shown = False
    for key in _SAFE_HINTS:
        value = meta.get(key)
        if value in (None, "", [], False):
            continue
        text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        print(f"  {key}: {text[:260]}")
        shown = True

    families = record_candidate_families({"input": "", "collection_meta": meta})
    if families:
        print(f"  possible moved family: {', '.join(families)}  (candidate only —")
        print("     verify against Notification 9/2025 before tagging)")
        shown = True

    if outcome := _ruling_outcome(record):
        print()
        print(f"  what the authority decided ({outcome.confidence}):")
        if outcome.headings:
            print(f"     heading(s): {', '.join(outcome.headings)}")
        print(f"     \"{outcome.quote[:300]}\"")
        print("     The HEADING is durable and usable. Any rate here is not:")
        print("     derive the slab from Notification 9/2025 yourself.")
        shown = True

    stale = meta.get("stale_rates_in_ruling")
    if stale:
        print()
        print(f"  !! rates stated in this ruling: {', '.join(stale)}")
        print("     These are PRE-22-Sep-2025 and must NOT be copied into the label.")
        print("     Take the heading from the ruling; derive the slab from Notif. 9/2025.")
        if "12" in stale:
            print("     Contains 12%, which no longer exists -> tag rate-changed-2025.")
        shown = True

    if shown:
        print(RULE)


def label_one(record: dict, ex_id: str) -> Example | None:
    """Collect one judgement. Returns None if skipped."""
    print("\n  slab:  [a] 0%    [b] 0.25%  [c] 1.5%  [d] 3%")
    print("         [e] 5%    [f] 18%    [h] 40%")
    print("         [u] UNANSWERABLE     [s] skip  [:q] save & quit")
    print("         (12% abolished 22 Sep 2025; 28% abolished 1 Feb 2026)")
    choice = _menu("  > ", SLAB_KEYS, extra={"u": UNANSWERABLE, "s": "__skip__"})
    if choice == "__skip__":
        return None

    answerable = choice != UNANSWERABLE
    notes = ""

    if not answerable:
        print("\n  reason:")
        for k, r in REASON_KEYS.items():
            print(f"         [{k}] {r}")
        reason = _menu("  > ", REASON_KEYS)
        missing = _ask("  which fact is missing?  > ")
        notes = f"reason={reason}; missing={missing}"

    hsn = _ask(
        "\n  hsn4 (4 digits" + ("" if answerable else ", blank if unknown") + ")  > ",
        allow_empty=not answerable,
    )
    hsn4 = hsn or None

    print("\n  difficulty:  [1] typical  [2] hard  [3] long_context  [4] adversarial  [5] out_of_scope")
    difficulty = _menu("  > ", DIFFICULTY_KEYS)

    justification = _ask("\n  justification (schedule entry + why this heading)\n  > ")

    raw_tags = _ask("  tags (comma-separated, blank for none)  > ", allow_empty=True)
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    if answerable:
        moved = _ask("  did this rate change on 22 Sep 2025? [y/N]  > ", allow_empty=True)
        if moved.lower().startswith("y") and "rate-changed-2025" not in tags:
            tags.append("rate-changed-2025")

    if answerable:
        extra_notes = _ask("  labeller notes (blank for none)  > ", allow_empty=True)
        notes = extra_notes

    step = _ask("  which procedure step resolved it? (1-7)  > ", allow_empty=True)
    if step:
        notes = (notes + "; " if notes else "") + f"step={step}"

    return Example(
        id=ex_id,
        input=record["input"],
        slab=choice,
        hsn4=hsn4,
        answerable=answerable,
        justification=justification,
        difficulty=difficulty,
        tags=tags,
        source=record.get("source", ""),
        source_id=record.get("source_id", ""),
        collected_at=record.get("collected_at", ""),
        labelled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        labeller_notes=notes,
        collection_meta=record.get("collection_meta", {}),
    )


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------


def select_queue(
    pool: list[dict],
    done_source_ids: set[str],
    *,
    keyword: str | None = None,
    source: str | None = None,
    stale: str | None = None,
    changed_candidates: bool = False,
    state: str | None = None,
    exclude_state: str | None = None,
    spread_states: bool = False,
) -> list[dict]:
    """Records still to label, narrowed by the requested filters.

    `stale` selects rulings that quote a given rate. Passing "12" queues the
    rulings whose slab was abolished on 22 Sep 2025 — by construction the
    `rate-changed-2025` examples, and the ones the headline finding rests on,
    so they are worth labelling first while the guideline is freshest.
    """
    queue = [r for r in pool if r.get("source_id") not in done_source_ids]

    if source:
        queue = [r for r in queue if r.get("source") == source]
    if stale:
        queue = [
            r
            for r in queue
            if stale in (r.get("collection_meta", {}).get("stale_rates_in_ruling") or [])
        ]
    if state:
        s = state.lower()
        queue = [r for r in queue if s in _state_of(r).lower()]
    if exclude_state:
        x = exclude_state.lower()
        queue = [r for r in queue if x not in _state_of(r).lower()]
    if changed_candidates:
        queue = _interleave_by_family([r for r in queue if record_candidate_families(r)])
    if keyword:
        k = keyword.lower()
        queue = [r for r in queue if k in r["input"].lower()]
    if spread_states:
        queue = _interleave(queue, _state_of)
    return queue


def _state_of(record: dict) -> str:
    return record.get("collection_meta", {}).get("state", "") or "(unknown)"


def _interleave(records: list[dict], key: Callable[[dict], str]) -> list[dict]:
    """Round-robin records across a grouping so an early stop still spreads.

    Both pools are lopsided: biscuits and chocolate are together about 60% of
    the rate-changed listing candidates, and Gujarat is 23 of the 31 rulings
    quoting the abolished slab. Labelling the first N in file order would make
    the headline finding a claim about biscuits, or about Gujarat packaging
    disputes. Interleaving means stopping at any point still leaves a spread.
    """
    buckets: dict[str, list[dict]] = {}
    for record in records:
        buckets.setdefault(key(record), []).append(record)

    ordered: list[dict] = []
    while buckets:
        for group in list(buckets):
            ordered.append(buckets[group].pop(0))
            if not buckets[group]:
                del buckets[group]
    return ordered


def _interleave_by_family(records: list[dict]) -> list[dict]:
    # First family only: each record takes one queue position.
    return _interleave(records, lambda r: record_candidate_families(r)[0])


def run_label(
    target_total: int,
    keyword: str | None,
    source: str | None = None,
    stale: str | None = None,
    changed_candidates: bool = False,
    *,
    state: str | None = None,
    exclude_state: str | None = None,
    spread_states: bool = False,
) -> int:
    labelled = list(read_jsonl(GOLDEN))
    done_source_ids = {e.source_id for e in labelled if e.source_id}

    pool = load_pool()
    if not pool:
        print(
            f"\n  No raw records in {RAW_DIR}/. Run `make collect` first.\n",
            file=sys.stderr,
        )
        return 1

    queue = select_queue(
        pool,
        done_source_ids,
        keyword=keyword,
        source=source,
        stale=stale,
        changed_candidates=changed_candidates,
        state=state,
        exclude_state=exclude_state,
        spread_states=spread_states,
    )
    active = [
        f"{k}={v!r}"
        for k, v in (
            ("filter", keyword),
            ("source", source),
            ("stale", stale),
            ("changed-candidates", changed_candidates or None),
            ("state", state),
            ("exclude-state", exclude_state),
            ("spread-states", spread_states or None),
        )
        if v
    ]
    if active:
        print(f"\n  {'  '.join(active)}: {len(queue)} candidates")

    if stale == "12":
        print(
            "\n  These rulings quote 12%, a slab abolished on 22 Sep 2025.\n"
            "  Take the heading from the ruling; derive the slab from Notification\n"
            "  9/2025 yourself. Tag each one rate-changed-2025."
        )

    if changed_candidates:
        print(
            "\n  CANDIDATES ONLY — these listings merely name a family announced\n"
            "  as moving on 22 Sep 2025 (data/reference/rate_changes_2025.md).\n"
            "  Many will not have moved: much of this was already at 0% or 5%,\n"
            "  and packaging conditionality (guideline §4a) decides first.\n"
            "  Establish the heading, derive the slab, and only then decide\n"
            "  whether to apply the rate-changed-2025 tag."
        )

    if not queue:
        print("\n  Nothing left to label with those settings.\n")
        return 0

    show_progress(labelled, target_total)
    written = 0
    try:
        for record in queue:
            # `labelled` already absorbs each saved row, so it alone is the
            # count — adding `written` here double-counts every save.
            batch_pos = len(labelled) % BATCH_SIZE + 1
            ex_id = next_id(labelled)

            present(record, ex_id, len(labelled) + 1, batch_pos)
            ex = label_one(record, ex_id)
            if ex is None:
                continue

            problems = validate_example(ex)
            if problems:
                print("\n  ! this row does not validate:")
                for p in problems:
                    print(f"      {p}")
                if not _ask("  keep it anyway? [y/N]  > ", allow_empty=True).lower().startswith("y"):
                    print("  discarded.")
                    continue

            append_jsonl(GOLDEN, [ex])
            labelled.append(ex)
            written += 1
            print(f"  saved {ex.id}")

            if written and (len(labelled) % BATCH_SIZE == 0):
                show_progress(labelled, target_total)
                print(
                    f"\n  Batch of {BATCH_SIZE} complete. Take a real break —\n"
                    "  fatigue shows up as self-disagreement, and self-disagreement\n"
                    "  is the ceiling on every model score you will publish.\n"
                )
                if not _ask("  continue? [y/N]  > ", allow_empty=True).lower().startswith("y"):
                    raise Quit
    except Quit:
        pass

    print(f"\n  Wrote {written} example(s) to {GOLDEN}.")
    show_progress(labelled, target_total)
    return 0


def run_relabel(n: int, seed: int | None) -> int:
    """Blind re-label for the self-agreement measurement (guideline §7.3)."""
    labelled = [e for e in read_jsonl(GOLDEN) if e.is_active]
    if len(labelled) < n:
        print(f"\n  Only {len(labelled)} labelled examples; need {n}.\n", file=sys.stderr)
        return 1

    out = Path(f"data/relabel-{date.today().isoformat()}.jsonl")
    already = {e.id for e in read_jsonl(out)}

    rng = random.Random(seed if seed is not None else date.today().toordinal())
    sample = rng.sample(labelled, n)
    todo = [e for e in sample if e.id not in already]

    print(
        f"\n  Blind re-label: {len(todo)} of {n} remaining -> {out}\n"
        "  Your original labels are NOT shown. Do not look them up.\n"
    )

    written = 0
    try:
        for i, orig in enumerate(todo, 1):
            record = {
                "input": orig.input,
                "source": orig.source,
                "source_id": orig.source_id,
                "collected_at": orig.collected_at,
                "collection_meta": orig.collection_meta,
            }
            present(record, orig.id, i, (i - 1) % BATCH_SIZE + 1)
            ex = label_one(record, orig.id)
            if ex is None:
                continue
            append_jsonl(out, [ex])
            written += 1
    except Quit:
        pass

    print(f"\n  Wrote {written} re-labels to {out}.")
    print(f"  Now run:  python -m harness.calibration.self_agreement --relabel {out}\n")
    return 0


def _accept(sug: Example, notes: dict) -> Example | None:
    """Take a grounded suggestion wholesale, asking only what it cannot know.

    Difficulty is a judgement about the example's place in the dataset, not
    about the goods, so the model has no basis for it and it is always asked.
    The rate-changed tag is confirmed rather than assumed, because the model
    infers it from the ruling's own stated rate — which in one real case was
    the applicant's rejected argument, not the holding.
    """
    print("\n  difficulty:  [1] typical  [2] hard  [3] long_context  "
          "[4] adversarial  [5] out_of_scope")
    difficulty = _menu("  > ", DIFFICULTY_KEYS)

    tags = [t for t in sug.tags if t != "rate-changed-2025"]
    if notes.get("rate_moved"):
        print(f"  model says the rate moved: {notes.get('rate_moved_basis', '')[:150]}")
        if _ask("  tag rate-changed-2025? [y/N]  > ", allow_empty=True).lower().startswith("y"):
            tags.append("rate-changed-2025")

    ex = Example(
        id=sug.id,
        input=sug.input,
        slab=sug.slab,
        hsn4=sug.hsn4,
        answerable=True,
        justification=sug.justification,
        difficulty=difficulty,
        tags=tags,
        source=sug.source,
        source_id=sug.source_id,
        collected_at=sug.collected_at,
        labelled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        labeller_notes="accepted model first pass after review",
        collection_meta=sug.collection_meta,
    )
    return ex


def run_review_first_pass(
    quarantine: Path,
    *,
    state: str | None = None,
    exclude_state: str | None = None,
    spread_states: bool = False,
    grounded_only: bool = False,
) -> int:
    """Review model first-pass suggestions into the golden set.

    Every row must be judged individually. A suggestion the annotator accepts
    is rewritten as `human-reviewed` and its `model_notes` are dropped; the
    quarantine file is left untouched, so the record of what the model proposed
    survives for the disclosure in the README.
    """
    pending = [e for e in read_jsonl(quarantine)]
    if not pending:
        print(f"\n  nothing in {quarantine}\n", file=sys.stderr)
        return 1

    labelled = list(read_jsonl(GOLDEN))
    done = {e.source_id for e in labelled if e.source_id}
    todo = [e for e in pending if e.source_id not in done]

    # Suggestions whose slab was read out of the archived Gazette are the ones
    # a review can accept in two keystrokes. Working those first is the fastest
    # honest route to a dataset worth running a model against.
    if grounded_only:
        todo = [e for e in todo if e.slab != UNCERTAIN and e.hsn4]

    # Same state controls as the labelling queue. Gujarat is 23 of the 31
    # rulings quoting the abolished slab, so reviewing in file order would make
    # the finding a claim about Gujarat.
    if state or exclude_state or spread_states:
        as_records = [
            {"collection_meta": e.collection_meta, "_ex": e} for e in todo
        ]
        if state:
            s = state.lower()
            as_records = [r for r in as_records if s in _state_of(r).lower()]
        if exclude_state:
            x = exclude_state.lower()
            as_records = [r for r in as_records if x not in _state_of(r).lower()]
        if spread_states:
            as_records = _interleave(as_records, _state_of)
        todo = [r["_ex"] for r in as_records]

    print(f"\n{RULE}")
    print(f"  Reviewing {len(todo)} model suggestion(s) of {len(pending)}.")
    print(f"  states: {dict(Counter(_state_of({'collection_meta': e.collection_meta}) for e in todo).most_common())}")
    print("  A suggestion is a starting point. The slab is YOUR judgement:")
    print("  derive it from Notification 9/2025, not from anything shown here.")
    print(RULE)

    written = 0
    try:
        for i, sug in enumerate(todo, 1):
            record = {
                "input": sug.input,
                "source": sug.source,
                "source_id": sug.source_id,
                "collected_at": sug.collected_at,
                "collection_meta": sug.collection_meta,
            }
            present(record, sug.id, i, (i - 1) % BATCH_SIZE + 1)

            notes = sug.model_notes or {}
            print("  --- model first pass (unreviewed) ---")
            print(f"     proposed heading: {sug.hsn4 or '(none)'}  "
                  f"[confidence: {notes.get('hsn_confidence', '?')}]")
            print(f"       basis: {notes.get('hsn_basis', '')}")
            print(f"     proposed slab:    {sug.slab}  "
                  f"[confidence: {notes.get('slab_confidence', '?')}]")
            print(f"       basis: {notes.get('slab_basis', '')}")
            if notes.get("rate_moved"):
                print("     rate moved: yes — the source slab was abolished")
            if notes.get("conditional"):
                print("     NOTE: the authority's determination is conditional")
            print(RULE)

            # A suggestion whose slab was read out of the archived Gazette
            # needs a decision, not re-typing. Accepting is still your
            # judgement — you are looking at the entry it was read from — but
            # it costs two keystrokes instead of seven answers.
            grounded = sug.slab != UNCERTAIN and sug.hsn4
            if grounded:
                print("  [a] accept as shown   [e] label it myself   "
                      "[s] skip   [:q] quit")
                choice = _ask("  > ").lower()
                if choice == "s":
                    continue
                if choice == "a":
                    ex = _accept(sug, notes)
                    if ex is None:
                        continue
                else:
                    ex = label_one(record, sug.id)
            else:
                ex = label_one(record, sug.id)

            if ex is None:
                continue

            ex.labelled_by = "human-reviewed"
            ex.labeller_notes = (
                (ex.labeller_notes + "; " if ex.labeller_notes else "")
                + "reviewed from model first pass"
            )
            problems = validate_example(ex)
            if problems:
                print("\n  ! this row does not validate:")
                for p in problems:
                    print(f"      {p}")
                if not _ask("  keep it anyway? [y/N]  > ", allow_empty=True).lower().startswith("y"):
                    print("  discarded.")
                    continue

            append_jsonl(GOLDEN, [ex])
            labelled.append(ex)
            written += 1
            print(f"  saved {ex.id} (human-reviewed)")
    except Quit:
        pass

    print(f"\n  Reviewed {written} row(s) into {GOLDEN}.")
    print(f"  {quarantine} is unchanged — it is the record of what was suggested.\n")
    show_progress(labelled, 400)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=int, default=400, help="target dataset size")
    ap.add_argument("--filter", type=str, default=None, help="only show inputs containing this")
    ap.add_argument("--source", choices=sorted(SOURCES), default=None)
    ap.add_argument(
        "--stale",
        metavar="RATE",
        default=None,
        help="only rulings quoting this rate; --stale 12 queues the abolished-slab "
        "examples that seed the rate-changed-2025 slice",
    )
    ap.add_argument(
        "--changed-candidates",
        action="store_true",
        help="listings naming a family announced as moving on 22 Sep 2025. "
        "A search aid for filling the rate-changed-2025 slice, NOT a label — "
        "many matches will not have moved",
    )
    ap.add_argument("--relabel", type=int, metavar="N", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--state", default=None, help="only rulings from this state")
    ap.add_argument(
        "--exclude-state",
        default=None,
        help="skip rulings from this state; Gujarat dominates the ruling pool",
    )
    ap.add_argument(
        "--spread-states",
        action="store_true",
        help="round-robin the queue across states so an early stop still spreads",
    )
    ap.add_argument(
        "--review-first-pass",
        nargs="?",
        const="data/first_pass.jsonl",
        default=None,
        metavar="FILE",
        help="review model first-pass suggestions into the golden set",
    )
    ap.add_argument(
        "--grounded-only",
        action="store_true",
        help="review only suggestions whose slab was read from the archived "
        "Gazette — these accept in two keystrokes",
    )
    args = ap.parse_args()

    if args.review_first_pass:
        return run_review_first_pass(
            Path(args.review_first_pass),
            state=args.state,
            exclude_state=args.exclude_state,
            spread_states=args.spread_states,
            grounded_only=args.grounded_only,
        )
    if args.relabel:
        return run_relabel(args.relabel, args.seed)
    return run_label(
        args.target,
        args.filter,
        args.source,
        args.stale,
        args.changed_candidates,
        state=args.state,
        exclude_state=args.exclude_state,
        spread_states=args.spread_states,
    )


if __name__ == "__main__":
    raise SystemExit(main())
