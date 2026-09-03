# Indian GST Rate-Slab Eval Harness

**Can a language model tell you what GST rate applies to a product — under the
rules that are actually in force?**

On **22 September 2025** India's GST slabs were restructured. Notification
9/2025–CT(Rate) superseded the 2017 schedule, the **12 % slab was abolished**,
and a 40 % demerit rate was introduced. Every model in this benchmark was
trained on a web that is still overwhelmingly describing the old table.

This repository is an open, human-labelled benchmark for classifying real Indian
product descriptions into the current GST slabs — and for measuring how often
models answer from a rate table that no longer exists.

> **Status: dataset in construction (week 1 of 6).** Nothing is claimed here
> that has not been measured. The leaderboard below is empty because no model
> has been run yet, and it will stay empty until one has been.

---

## Results

_No models have been run. This section will contain the leaderboard._

| Model | Version | Run date | Slab acc. | HSN-4 acc. | **Stale-slab rate** | Abstention F1 | ₹/correct | p50 latency |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

**Human ceiling:** _pending the self-agreement measurement (week 3)._

---

## The headline finding

_Pending. Will be written only once the numbers exist._

The hypothesis under test — chosen before any model was run, and recorded here
so it cannot be retrofitted:

> Frontier models will classify goods into the **pre-September-2025** slab
> structure, emitting the abolished 12 % rate on a measurable share of items,
> and will do so with no drop in stated confidence.

If that turns out to be false, this section will say so.

---

## Why this task

| Criterion | How this task meets it |
|---|---|
| **Narrow enough to label** | One product description in, one slab out. |
| **Real, messy data** | Open Food Facts India, advance rulings, government catalogues. Nothing synthetic — see [`data/DATA_LICENCE.md`](data/DATA_LICENCE.md). |
| **Not already benchmarked** | No public GST/HSN benchmark exists. The nearest work, [ATLAS](https://arxiv.org/pdf/2509.18400), covers **US** HTS codes. |
| **Verifiable** | Ground truth is a published legal instrument, not an opinion. |
| **Has a hard core** | Pre-packaged-and-labelled conditionality, GRI 3 sets, parts rules, and a rate table that moved under the models' feet. ATLAS reached only 40 % exact at the 10-digit level, so this will not be a leaderboard where everything scores 97 %. |

---

## Methodology

### Dataset

- **Target size** 400 examples. Below ~200 the confidence intervals are too wide
  to support any claim; past ~600 the labelling cost stops buying information.
- **Stratified, not sampled**: 40 % typical · 25 % hard · 15 % long-context ·
  10 % adversarial · 10 % **unanswerable**.
- That last stratum is the point. Models that answer confidently when the
  description does not determine a rate fail in production, and almost no
  benchmark tests for it.
- **Labelled by hand, against the primary notification.** No model assistance at
  any stage, including first passes and tie-breaking — see
  [`data/guideline.md`](data/guideline.md) §7.5.
- Examples are **never edited in place**. A correction is appended under a new
  id and the old row carries `deprecated_by`.

Ground truth authority: [`data/reference/rate_schedule.md`](data/reference/rate_schedule.md).
Annotation protocol: [`data/guideline.md`](data/guideline.md).

### Scoring

Cheapest method that works, escalating only where forced:

| Field | Method | Why |
|---|---|---|
| `slab` | **Exact match** | Closed label set. Free, fast, unarguable. |
| `hsn4` | **Exact match**, plus 2-digit chapter as partial credit | Structured. |
| `answerable` | **Exact match**, reported as abstention precision/recall | Binary. |
| `justification` | **LLM-as-judge** | Genuinely open-ended — the only place a judge is warranted. |

A benchmark that judges everything with an LLM has reached for the fashionable
tool. Three of the four fields here never touch a judge.

### Judge calibration

Planned for week 5, on 100 examples, reported whatever the result:
Cohen's kappa, the full confusion matrix, and **every disagreement categorised
by cause**. A low kappa that is diagnosed is a better result than a high one
that is not, so it will be published either way.

| kappa | Reading |
|---|---|
| < 0.40 | Judge is unusable. Fix the rubric. |
| 0.40–0.60 | Moderate. Usable with caveats, stated. |
| 0.60–0.80 | Substantial. A good result. |
| > 0.80 | Strong — check the task has not been made trivially easy. |

### Cost

Every call logs `tokens_in`, `tokens_out`, `latency_ms`, `provider`, `model`
and per-1k prices, so the leaderboard can report the metric almost nobody
publishes:

```
cost_per_correct_answer = total_cost / number_of_correct_answers
```

This reorders leaderboards. A model at 84 % for ₹0.30 per correct answer beats
one at 89 % for ₹2.10 in most real deployments.

_Prices will be stated with the date they were read._

---

## Reproducing

Python 3.11+. No dependencies are needed for the dataset tooling.

```bash
make collect     # rebuild the raw corpus from public sources
make validate    # schema + composition checks on the golden set
make test        # unit tests
```

Model runs (week 4 onward) need API keys; copy `.env.example` to `.env`.

---

## Limitations

Written honestly, and expanded as the work proceeds.

- **Single annotator.** Self-agreement bounds this dataset, but it cannot detect
  a mistake made consistently. A second annotator would; there isn't one.
- **Ground truth has a shelf life.** GST notifications are amended. Labels are
  correct as of the date in `data/reference/rate_schedule.md` and no longer.
- **Schedule VII / 40 % transition is unsettled**, so tobacco, pan masala,
  aerated beverages and cement are excluded from v1.0 rather than labelled with
  a rate that may be wrong for reasons outside the annotator's control.
- **Source skew.** Open Food Facts is packaged food, so the corpus over-weights
  Chapters 1–24. Advance rulings and government catalogues are being added to
  correct this; until they are, results generalise to groceries and not to goods
  at large.
- **Descriptions are reassembled** from catalogue fields (brand, name, quantity,
  packaging), which is tidier than a real marketplace listing. Concatenation
  only — no text is generated — but it is not identical to production input.
- **Goods only.** Services are out of scope.

---

## Licence

Code: MIT — see [`LICENSE`](LICENSE).
Dataset: **ODbL 1.0**, being a derived database of Open Food Facts.
Provenance for every example: [`data/DATA_LICENCE.md`](data/DATA_LICENCE.md).

> Contains information from Open Food Facts, made available under the
> [Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/).
