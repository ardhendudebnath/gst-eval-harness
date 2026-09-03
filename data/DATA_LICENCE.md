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
| `aar` | GST Advance Ruling (AAR / AAAR) decisions, state authorities | Government of India public documents | **Excerpt only**, ≤ 300 words, with citation |
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

### Advance Rulings

AAR and AAAR decisions are published decisions of statutory authorities and are
public documents. This repository reproduces only the **product-description
passage** at issue in a ruling — never the full decision — together with the
ruling reference so any reader can retrieve the original.

Applicant names, GSTINs, addresses and any other party-identifying detail are
removed at collection time (§3). The benchmark is about the goods, not the
taxpayers, and nothing is lost by stripping them.

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
`collection_meta`:

1. Unicode NFKC normalisation; collapse runs of whitespace.
2. Strip marketing furniture that carries no classification signal — `Buy Now`,
   `Free Delivery`, `⭐ Best Seller`, star-rating glyphs, emoji runs.
3. Strip URLs, e-mail addresses and phone numbers.
4. Strip applicant-identifying detail from `aar` excerpts.
5. Drop records shorter than 8 characters or longer than 12,000 characters.
6. Drop the out-of-scope families listed in `guideline.md` §4d (tobacco, pan
   masala, aerated beverages, cement, services).

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
