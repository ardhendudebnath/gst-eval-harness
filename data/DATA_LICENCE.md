# Data provenance and licence

Every example in `golden.jsonl` carries a `source` field naming one of the
sources below. This file states where each came from, under what licence, and
whether the source text is redistributed in this repository or fetched by the
reader.

**Nothing in this dataset is synthetic.** No product description was written or
paraphrased by a language model. Descriptions are reproduced as collected, with
only the normalisation described in §3.

---

## 1. Sources

| Key | Source | Licence | Redistributed here? |
|---|---|---|---|
| `off` | [Open Food Facts](https://world.openfoodfacts.org/) — India subset | Database: **ODbL 1.0**; individual facts: **DbCL 1.0** | **Yes**, text inline |
| `aar` | GST Advance Ruling decisions, via the [GST Council index](https://gstcouncil.gov.in/authority-for-advance-ruling) | Public orders of statutory authorities | **Excerpt only** — see §1.2 — with citation and a link to the full order |
| `ogd` | [data.gov.in](https://data.gov.in/) product & price catalogues | **GODL-India** | **Yes**, text inline |
| `gem` | Government e-Marketplace public product catalogue | Government of India public catalogue | **ID + fetch script only** |

### Attribution required by ODbL (Open Food Facts)

> Contains information from **Open Food Facts**, made available under the
> [Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/).

Because Open Food Facts is ODbL and this dataset is a derived database of it,
the **`golden.jsonl` file is itself published under ODbL 1.0**. The harness
*code* is separately licensed under MIT — see `../LICENSE`. Keeping the code and
data licences distinct is deliberate; ODbL's share-alike attaches to the
database, not to the software that reads it.

### 1.2 Advance Rulings

Advance rulings are orders of statutory authorities constituted under
s.96 of the CGST Act, published by the GST Council for public reference.

This repository reproduces only the **statement-of-facts passage** describing
the goods — never the full order, and never the authority's findings or the
ruling itself. Two excerpt tiers:

| Tier | Cap | Used for |
|---|---|---|
| default | 300 words | most strata |
| `--long` | 1,200 words | the `long_context` stratum |

Every example records `ruling_url`, so the complete order is one click away and
this repository never becomes a substitute for the source.

**Party-identifying detail is removed at collection time** (§3): applicant
names in both prose (`M/s ...`) and labelled-table form, postal addresses,
GSTINs, Application Reference Numbers, and the names of representatives who
appeared. The benchmark is about the goods, not the taxpayers.

Redaction is deliberately over-inclusive. Many of these PDFs are OCR'd, and the
OCR damages exactly the tokens that identify people — one real GSTIN came back
as `24ABCDE1234FlZ5`, with letter `l` substituted for digit `1`, which a strict
GSTIN grammar does not match. The patterns therefore match on *shape* rather
than exact grammar. Over-matching costs a few characters of goods description;
under-matching leaks a taxpayer identifier.

---

## 2. What is *not* here

- **No scraped marketplace listings.** Amazon, Flipkart, Meesho and similar sites
  prohibit scraping in their terms of use. No example in this dataset comes from
  them, regardless of how convenient the data would have been.
- **No personal information.** These are product catalogues. The one place party
  names could appear is in advance rulings, and they are stripped.
- **No LLM-generated or LLM-paraphrased text**, in the inputs or the labels.

---

## 3. Normalisation applied at collection

Applied uniformly by `harness/collect/`, and recorded per-example in
`collection_meta.transforms` — so each row states which transforms actually
fired on it, not merely which ones exist.

1. Unicode NFKC normalisation; collapse runs of whitespace.
2. Strip marketing furniture that carries no classification signal — `Buy Now`,
   `Free Delivery`, `⭐ Best Seller`, star-rating glyphs, emoji runs.
3. Strip URLs, e-mail addresses and phone numbers.
4. Strip party-identifying detail from `aar` excerpts (§1.2).
5. Strip procedural furniture from `aar` excerpts — `Page 3 of 8`, appeal-notice
   paragraphs, admissibility recitals. This is the exact analogue of step 2 for
   legal text: it carries no classification signal, and leaving it in would pad
   every input by a few hundred tokens, inflating the cost-per-correct-answer
   figure this benchmark reports.
6. Drop records shorter than 8 characters or longer than 12,000 characters.
7. Drop the out-of-scope families listed in `guideline.md` §4d (tobacco, pan
   masala, aerated beverages, cement, alcohol) and, for `aar`, drop services
   rulings — s.97(2)(a) covers "goods **or services** or both", so the clause
   alone does not select goods.

**What is not normalised.** OCR damage in ruling text — `t he case`,
`pro priet orship`, `lsabgol` for `Isabgol` — is left exactly as extracted.
It is real input noise of the kind a production system meets, and repairing it
would make the corpus partly synthetic.

Original text is **not** discarded — raw pulls land in `data/raw/`, which is
git-ignored. `make collect` reproduces it from scratch.

---

## 4. Reproducing the corpus

```bash
make collect
```

This repopulates `data/raw/` from the live sources. Because upstream catalogues
change, a rebuild will not be byte-identical to the original pull. Each example
in `golden.jsonl` therefore records `collected_at` and a `source_id` stable
enough to retrieve the original record.

**Corpus first collected:** _pending first run._

---

## 5. Removal requests

If you hold rights in any record reproduced here and want it removed, open an
issue in this repository. Examples are removed on request without argument, and
the removal is recorded in the dataset changelog rather than being made silently.
