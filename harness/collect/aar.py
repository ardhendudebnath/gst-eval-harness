"""Collect goods descriptions from GST Advance Ruling (AAR) decisions.

Open Food Facts supplies the `typical` stratum and nothing else: every record
is packaged food, so the whole pool sits in HSN Chapters 1-24 and the
descriptions are a dozen words long. Advance rulings supply what it cannot —
technical goods across the whole tariff, long documents for the `long_context`
stratum, and applicant contentions that argue for a heading the authority then
rejects, which is exactly the distractor content the `adversarial` stratum wants.

Source: the GST Council's national index at
https://gstcouncil.gov.in/authority-for-advance-ruling

Two properties of the source make this tractable:

  * The index's "Category" column is the **CGST s.97(2) clause** the application
    was filed under, and **97(2)(a) is "classification of any goods or services
    or both"**. Filtering on it selects classification rulings authoritatively
    rather than by keyword guesswork.

  * Roughly half the PDFs are scans with no text layer. They are detected by
    extracted-characters-per-page and skipped, not silently emitted as empty.

**The stale-rate hazard.** Most published rulings predate 22 September 2025, so
any GST rate they state is from the superseded schedule. The HSN heading a
ruling determines is still good — HSN is the Customs Tariff and GST 2.0 did not
touch it — but the rate is not. Rates found in a ruling are therefore recorded
under `stale_rates_in_ruling` and must never be copied into a label; the slab is
re-derived from Notification 9/2025. See data/guideline.md §2.

    python -m harness.collect.aar --pages 40 --out data/raw/aar.jsonl

Needs pypdf:  pip install -e ".[collect]"
"""

from __future__ import annotations

import argparse
import html as htmllib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.collect.http import fetch, fetch_text
from harness.collect.normalise import normalise
from harness.schema import out_of_scope_term

BASE = "https://gstcouncil.gov.in"
INDEX = BASE + "/authority-for-advance-ruling?page={page}"
CACHE = Path("data/cache/aar")

#: Below this many extracted characters per page, the PDF is a scan with no
#: text layer. Observed: real text runs 1700-2700 chars/page; scans yield 0-2.
MIN_CHARS_PER_PAGE = 200

#: DATA_LICENCE.md caps ordinary excerpts; --long raises it for the
#: long_context stratum.
DEFAULT_MAX_WORDS = 300
LONG_MAX_WORDS = 1200

# --- index parsing --------------------------------------------------------

_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(
    r'<td[^>]*class="views-field views-field-([a-z0-9-]+)"[^>]*>(.*?)</td>', re.S
)
_PDF_HREF = re.compile(r'href="([^"]+\.pdf)"', re.I)
_TAGS = re.compile(r"<[^>]+>")
#: The index publishes each file's size — "(Format: pdf, Size: 2.01 MB)".
_SIZE = re.compile(r"Size:\s*([\d.]+)\s*(KB|MB|GB)", re.I)
_SIZE_UNITS = {"kb": 1 / 1024, "mb": 1.0, "gb": 1024.0}

#: s.97(2)(a) — classification of goods. The clause list is written many ways
#: ("97(2) (a)", "97(2)(a),(b)", "97 (2) (a) (e)"), so match the clause letter
#: rather than the whole string.
_CLAUSE_A = re.compile(r"97\s*\(\s*2\s*\)[^a-z]*\(\s*a\s*\)", re.I)

#: Fallback for rows whose category is blank or bare "97(2)".
_CLASSIFICATION_HINTS = (
    "classif",
    "hsn",
    "chapter heading",
    "tariff item",
    "tariff heading",
    "rate of tax",
    "rate of gst",
    "gst rate",
)

#: s.97(2)(a) reads "classification of any goods **or services** or both", so the
#: clause alone does not select goods. Without this screen the pool fills with
#: construction contracts, club memberships and transformer repair — all real
#: classification disputes, none of them goods. Services are Chapter 99 (SAC)
#: and out of scope per guideline.md §1.
# The tax is called the "Goods and Services Tax", so the word "service" appears
# in literally every ruling. Neutralise the statute's own name before screening,
# or the word is pure noise.
_STATUTE_NAME = re.compile(
    r"Goods?\s+and\s+Services?\s+(?:Tax\s+)?(?:Act|Rules)?|GST\s+Act", re.I
)

#: STRONG signals: unambiguous even inside 1,200 words of legal prose, so they
#: are safe to look for in the facts as well as the brief.
_SERVICE_STRONG = re.compile(
    r"\b(?:works\s+contract|job\s*work|EPC\s+contract|turnkey"
    r"|erection[,\s]+testing|supply\s+of\s+services?\b|SAC\s+code"
    # "Government Entity" and "Government Authority" are concessional-rate
    # concepts from Notification 11/2017, so a ruling turning on whether a body
    # qualifies is a works-contract ruling. Measured over the corpus, these
    # four alternations drop exactly four records and all four are services.
    r"|Government\s+(?:Entity|Authority)|limb\s+of\s+(?:the\s+)?Government"
    r"|execution\s+of\s+(?:the\s+)?work)\b"
    r"|\bwork(?:s)?\b[^.]{0,40}\b(?:executed|awarded)\b",
    re.I,
)

#: WEAK signals: trustworthy only in the Council's curated one-line brief. In
#: the facts they fire on ordinary goods language — "catering to a global
#: clientele", "put in storage bins", "for storage of water bodies" — and
#: dropped seven genuine goods rulings before this split existed.
_SERVICE_WEAK = re.compile(
    r"\b(?:services?|renting|rental|leasing|lease|transport(?:ation)?\s+of"
    r"|consultancy|repair(?:ing|s)?|maintenance|installation|manpower"
    r"|catering(?!\s+to)|canteen|hostel|accommodation|admission|training|coaching"
    r"|tour\s+operator|commission\s+agent|lodging|boarding\s+house|printing"
    r"|storage|warehousing|hiring|erection|commissioning)\b",
    re.I,
)

#: Notification 11/2017-CT(Rate) prescribes rates for **services**; goods are
#: 1/2017 and now 9/2025. A ruling turning on an entry in 11/2017 is a services
#: ruling however its brief is worded — two Odisha orders about "Entry 3(vi) of
#: Notification No.11/2017" reached the pool with no service word in the brief
#: at all.
_SERVICE_NOTIFICATION = re.compile(
    r"\b11\s*/\s*2017\s*[-–—]?\s*(?:CT|C\.?T\.?|Central\s+Tax|IT|Integrated\s+Tax)",
    re.I,
)

# --- ruling text segmentation ---------------------------------------------

#: Where the applicant's account of the goods begins. Authorities format
#: rulings differently, so several openings are recognised; the West Bengal
#: "The Applicant is stated to be ..." form in particular sits after an
#: admissibility preamble that must not be mistaken for the facts.
_GOODS_START = re.compile(
    r"(?:"
    r"[Bb]rief\s+facts?(?:\s+of\s+the\s+case)?\s*:?"
    r"|[Ss]tatement\s+of\s+(?:relevant\s+)?facts"
    r"|[Tt]he\s+[Aa]pplicant\s+is\s+stated\s+to\s+be"
    r"|[Tt]he\s+[Aa]pplicant[^.]{0,120}?submitted\s+that"
    r"|[Tt]he\s+[Aa]pplicant\s+is\s+(?:a\s+|an\s+)?[^.]{0,60}?engaged\s+in"
    r"|applicant\s+is\s+engaged\s+in"
    r"|[Tt]he\s+[Aa]pplicant\s+(?:manufactures|produces|deals\s+in|proposes\s+to)"
    r")",
    re.S,
)

#: Where the authority's own reasoning starts. Everything from here on is the
#: answer, so the excerpt stops before it.
_GOODS_END = re.compile(
    r"(?:"
    r"\bDISCUSSION\b"
    r"|\bFINDINGS?\b"
    r"|\bPERSONAL\s+HEARING\b"
    r"|\bRULING\b"
    r"|\bWe\s+have\s+(?:gone\s+through|considered|carefully)"
    r"|\bQUESTIONS?\s+(?:ON\s+WHICH|RAISED)"
    r")",
    re.S,
)

#: Minimum words in a usable excerpt. Below this the segmentation has almost
#: certainly landed in boilerplate rather than the facts.
MIN_EXCERPT_WORDS = 25

#: Applications withdrawn or thrown out before a determination. One reached the
#: pool where the applicant withdrew "quoting the reason that there was an
#: inadvertent mistake in their application with regard to manufacturing
#: process" — the goods description is disowned by the person who wrote it, and
#: no authority ever ruled on it. Labelling that wastes annotator effort and
#: puts an example in the golden set whose facts nobody stands behind.
_WITHDRAWN = re.compile(
    r"\b(?:request(?:ed)?\s+(?:to\s+|for\s+)?withdraw"
    r"|permitted\s+to\s+withdraw"
    r"|withdrawn\s+by\s+the\s+applicant"
    r"|application\s+is\s+(?:hereby\s+)?withdrawn"
    r"|not\s+maintainable"
    r"|rejected\s+as\s+inadmissible)\b",
    re.I,
)


def is_withdrawn(text: str) -> bool:
    return bool(_WITHDRAWN.search(text))

_HSN = re.compile(
    r"\b(?:HSN|H\.?S\.?N\.?|heading|chapter|tariff\s+item|sub-?heading)"
    r"[^0-9\n]{0,25}(\d{4}(?:\s?\d{2}){0,2})",
    re.I,
)
_RATE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")

_DEDUPE_RE = re.compile(r"[^a-z0-9]+")


def dedupe_key(text: str) -> str:
    """Content key for near-duplicate detection.

    Deduplicating on `source_id` alone is not enough: the same ruling is
    published more than once under different filenames (one Cryo Container
    ruling arrived twice), and a benchmark that scores the same item twice
    overstates whatever a model does with it.
    """
    return _DEDUPE_RE.sub("", text.lower())[:400]


def _strip_html(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(_TAGS.sub(" ", fragment))).strip()


def parse_index_page(html: str) -> list[dict]:
    """Extract one index page's rows. Rows without cells (the header) are skipped."""
    rows: list[dict] = []
    for raw in _ROW.findall(html):
        cells = {k: _strip_html(v) for k, v in _CELL.findall(raw)}
        if not cells:
            continue
        href = _PDF_HREF.search(raw)
        size_m = _SIZE.search(cells.get("field-upload-file", ""))
        size_mb = (
            float(size_m.group(1)) * _SIZE_UNITS[size_m.group(2).lower()]
            if size_m
            else None
        )
        rows.append(
            {
                "applicant": cells.get("title", ""),
                "state": cells.get("field-states-ut", ""),
                "brief": cells.get("body", ""),
                "order_no": cells.get("field-order-no-date", ""),
                "category": cells.get("field-category", ""),
                "pdf": href.group(1) if href else None,
                "size_mb": size_mb,
            }
        )
    return rows


def is_about_services(row: dict, excerpt: str = "") -> bool:
    """True when the ruling is about services rather than goods.

    Two tiers, because the brief and the facts are different kinds of text.
    The brief is a curated one-liner where "services" means something; the
    facts are 1,200 words of legal prose where it is noise. So strong,
    unambiguous phrases are looked for in both, and the softer vocabulary only
    in the brief.
    """
    brief = row.get("brief", "")
    strong_hay = _STATUTE_NAME.sub(" ", scope_text(excerpt, brief))
    if _SERVICE_STRONG.search(strong_hay) or _SERVICE_NOTIFICATION.search(strong_hay):
        return True
    return bool(_SERVICE_WEAK.search(_STATUTE_NAME.sub(" ", brief)))


def is_classification(row: dict) -> bool:
    """True when the row is a classification-of-**goods** ruling.

    Two independent conditions, both required:

      * it is a classification question — the s.97(2)(a) clause in the Category
        column, or failing that, classification language in the brief; and
      * it is about goods rather than services, since s.97(2)(a) covers both.
    """
    if is_about_services(row):
        return False
    if _CLAUSE_A.search(row.get("category", "")):
        return True
    brief = row.get("brief", "").lower()
    return any(hint in brief for hint in _CLASSIFICATION_HINTS)


# --- PDF ------------------------------------------------------------------


def _load_pypdf():
    try:
        import pypdf
    except ImportError:  # pragma: no cover - environment-dependent
        print(
            "\n  This collector needs pypdf:\n"
            '      pip install -e ".[collect]"\n'
            "  (the rest of the harness stays dependency-free)\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return pypdf


def extract_pdf_text(raw: bytes) -> tuple[str, int]:
    """Return (text, page_count). Empty text means unparseable."""
    pypdf = _load_pypdf()
    import logging

    # pypdf is chatty about recoverable structural damage in these files
    # ("incorrect startxref pointer"); the text still comes out fine.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        pages = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return text, pages
    except Exception:
        return "", 0


def is_scanned(text: str, pages: int) -> bool:
    """A scan has no text layer, so extraction yields almost nothing per page."""
    if pages <= 0:
        return True
    return len(text) / pages < MIN_CHARS_PER_PAGE


def segment_goods_description(text: str, max_words: int) -> tuple[str, bool] | None:
    """Pull the applicant's account of the goods out of a ruling.

    Returns (excerpt, truncated), or **None** when the facts section cannot be
    located. Returning None matters: an earlier version fell back to skipping a
    fixed number of header characters, which reliably produced excerpts that
    began mid-word inside appeal boilerplate ("cordance with Section 100(3)...")
    and carried the applicant's name and postal address instead of any goods.
    A smaller corpus beats a corpus of boilerplate.

    The excerpt stops before the authority's reasoning so it cannot contain the
    answer. The applicant's *proposed* heading is deliberately kept — the
    authority frequently rejects it, and that rejected contention is what makes
    these examples adversarial.
    """
    start_m = _GOODS_START.search(text)
    if not start_m:
        return None
    start = start_m.start()

    end_m = _GOODS_END.search(text, start + 40)
    end = end_m.start() if end_m else len(text)

    excerpt = text[start:end].strip()
    words = excerpt.split()
    if len(words) < MIN_EXCERPT_WORDS:
        return None

    truncated = len(words) > max_words
    if truncated:
        excerpt = " ".join(words[:max_words])
    return excerpt, truncated


def _hsn_candidates(text: str) -> list[str]:
    """Tariff codes mentioned in the ruling, as a research hint for the annotator.

    Statute years are excluded: "Customs Tariff Act, 1975" and "the CTA, 1985"
    sit close enough to the word "Tariff" to be picked up as headings otherwise.
    No HSN chapter reaches 19, so any 4-digit code starting 19 or 20 is a year.
    """
    seen: list[str] = []
    for m in _HSN.finditer(text):
        code = re.sub(r"\s+", "", m.group(1))[:8]
        if len(code) == 4 and code.startswith(("19", "20")):
            continue
        if len(code) >= 4 and code not in seen:
            seen.append(code)
    return seen[:12]


def _stale_rates(text: str) -> list[str]:
    plausible = {"0", "0.25", "1.5", "3", "5", "12", "18", "28", "40"}
    return sorted({r for r in _RATE.findall(text) if r in plausible})


# --- collection -----------------------------------------------------------


def _cache_path(pdf_href: str) -> Path:
    return CACHE / Path(pdf_href).name


def _get_pdf(pdf_href: str) -> bytes | None:
    cached = _cache_path(pdf_href)
    if cached.exists():
        return cached.read_bytes()
    try:
        raw = fetch(BASE + pdf_href, timeout=120)
    except Exception as exc:  # noqa: BLE001 - report and move on
        print(f"    fetch failed: {exc}", file=sys.stderr)
        return None
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(raw)
    time.sleep(1.5)
    return raw


def collect(
    pages: int,
    out_path: Path,
    max_words: int,
    start_page: int = 0,
    max_size_mb: float = 1.5,
) -> int:
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                seen_ids.add(rec["source_id"])
                seen_keys.add(dedupe_key(rec["input"]))
        print(f"resuming — {len(seen_ids)} rulings already collected", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    written = 0
    stats = {
        "rows": 0,
        "classification": 0,
        "too_big": 0,
        "scanned": 0,
        "no_pdf": 0,
        "fetch_failed": 0,
        "withdrawn": 0,
        "services": 0,
        "no_facts_section": 0,
        "too_short": 0,
        "out_of_scope": 0,
        "duplicate": 0,
        "already_had": 0,
    }

    with out_path.open("a", encoding="utf-8") as fh:
        for page in range(start_page, start_page + pages):
            try:
                html = fetch_text(INDEX.format(page=page))
            except Exception as exc:  # noqa: BLE001
                print(f"page {page}: {exc}\n  stopping; re-run to resume", file=sys.stderr)
                break

            rows = parse_index_page(html)
            if not rows:
                print(f"page {page}: no rows, stopping", file=sys.stderr)
                break
            stats["rows"] += len(rows)

            kept = 0
            for row in rows:
                if not is_classification(row):
                    continue
                stats["classification"] += 1

                if not row["pdf"]:
                    stats["no_pdf"] += 1
                    continue

                source_id = Path(row["pdf"]).name
                if source_id in seen_ids:
                    stats["already_had"] += 1
                    continue

                # Scans are image-heavy and large; text rulings are usually
                # well under a megabyte. Skipping big files before downloading
                # avoids pulling multi-megabyte scans only to discard them.
                # It is a soft signal — some large files do carry text — so it
                # trades a little recall for a lot of bandwidth.
                if (
                    max_size_mb
                    and row.get("size_mb")
                    and row["size_mb"] > max_size_mb
                    and not _cache_path(row["pdf"]).exists()
                ):
                    stats["too_big"] += 1
                    continue

                raw = _get_pdf(row["pdf"])
                if raw is None:
                    stats["fetch_failed"] += 1
                    continue

                text, n_pages = extract_pdf_text(raw)
                if is_scanned(text, n_pages):
                    stats["scanned"] += 1
                    continue

                if is_withdrawn(text):
                    stats["withdrawn"] += 1
                    continue

                segmented = segment_goods_description(text, max_words)
                if segmented is None:
                    stats["no_facts_section"] += 1
                    continue
                excerpt, truncated = segmented

                cleaned, applied = normalise(excerpt, is_ruling=True)
                if len(cleaned.split()) < MIN_EXCERPT_WORDS:
                    stats["too_short"] += 1
                    continue
                # Second services screen, now that the facts are available. The
                # first one saw only the brief, which can describe a works
                # contract purely by notification entry.
                if is_about_services(row, cleaned):
                    stats["services"] += 1
                    continue

                if term := out_of_scope_term(scope_text(cleaned, row["brief"])):
                    stats["out_of_scope"] += 1
                    continue

                key = dedupe_key(cleaned)
                if key in seen_keys:
                    stats["duplicate"] += 1
                    continue

                seen_ids.add(source_id)
                seen_keys.add(key)
                fh.write(
                    json.dumps(
                        {
                            "source": "aar",
                            "source_id": source_id,
                            "input": cleaned,
                            "collected_at": now,
                            "collection_meta": {
                                "transforms": applied,
                                "state": row["state"],
                                "order_no": row["order_no"],
                                "category": row["category"],
                                "ruling_brief": row["brief"][:600],
                                "ruling_url": BASE + row["pdf"],
                                "pdf_pages": n_pages,
                                "truncated": truncated,
                                "hsn_candidates": _hsn_candidates(text),
                                # Pre-GST-2.0 in most rulings. Never copy into a
                                # label; re-derive the slab from Notif. 9/2025.
                                "stale_rates_in_ruling": _stale_rates(text),
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                kept += 1
                written += 1

            print(f"page {page}: {len(rows)} rows, kept {kept}", file=sys.stderr)
            time.sleep(1.5)

    print(f"\nstats: {stats}", file=sys.stderr)
    return written


#: Words of the excerpt that count as "what this ruling is about" for scope
#: screening. Raising the excerpt cap to 1200 words made whole-excerpt
#: screening wrong: a ruling about industrial machinery that mentions a cement
#: plant as a customer on page four is not a ruling about cement, but a
#: whole-text match discards it. A ruling that *is* about an excluded family
#: says so in its brief and its opening facts.
SCOPE_HEAD_WORDS = 200


def scope_text(excerpt: str, brief: str = "") -> str:
    """The part of a ruling that determines its subject, for scope screening."""
    return f"{brief} {' '.join(excerpt.split()[:SCOPE_HEAD_WORDS])}"


def cached_pdf_for(record: dict) -> Path:
    """Where this record's source PDF lives, whether or not it is present."""
    href = record.get("collection_meta", {}).get("ruling_url", "")
    return CACHE / (record.get("source_id") or Path(href).name)


def reextract(record: dict, max_words: int) -> dict | None:
    """Rebuild one collected record's excerpt from its cached PDF.

    The word cap is a policy choice, not a property of the source, so changing
    it must not mean re-crawling: the PDF is already on disk and the index
    metadata is already in the record.

    Returns None when the record should not survive — the PDF is a scan, the
    application was withdrawn, or no facts section can be found. Callers must
    check `cached_pdf_for()` first and leave the record alone when the PDF is
    simply absent: `data/cache/` is git-ignored, so on a fresh clone every PDF
    is missing and treating that as failure would delete the whole pool.
    """
    cached = cached_pdf_for(record)
    if not cached.exists():
        return None

    text, pages = extract_pdf_text(cached.read_bytes())
    if is_scanned(text, pages) or is_withdrawn(text):
        return None

    segmented = segment_goods_description(text, max_words)
    if segmented is None:
        return None
    excerpt, truncated = segmented

    cleaned, applied = normalise(excerpt, is_ruling=True)
    if len(cleaned.split()) < MIN_EXCERPT_WORDS:
        return None

    updated = dict(record)
    updated["input"] = cleaned
    meta = dict(record.get("collection_meta", {}))
    meta["transforms"] = applied
    meta["truncated"] = truncated
    meta["max_words"] = max_words
    updated["collection_meta"] = meta
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--start-page", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("data/raw/aar.jsonl"))
    ap.add_argument(
        "--long",
        action="store_true",
        help=f"allow up to {LONG_MAX_WORDS}-word excerpts for the long_context stratum",
    )
    ap.add_argument("--max-words", type=int, default=None)
    ap.add_argument(
        "--max-size-mb",
        type=float,
        default=1.5,
        help="skip PDFs larger than this without downloading (0 disables; "
        "large files are usually scans with no text layer)",
    )
    args = ap.parse_args()

    max_words = args.max_words or (LONG_MAX_WORDS if args.long else DEFAULT_MAX_WORDS)

    n = collect(args.pages, args.out, max_words, args.start_page, args.max_size_mb)
    print(f"wrote {n} new rulings to {args.out}", file=sys.stderr)
    print(
        "Source: GST Council advance ruling index. Excerpts only, with citation; "
        "full orders remain at gstcouncil.gov.in.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
