# Indian GST Rate-Slab Eval Harness

**Can a language model tell you what GST rate applies to a product — under the
rules that are actually in force?**

India's GST slabs were restructured twice in under two years. Notification
9/2025–CT(Rate) superseded the 2017 schedule on **22 September 2025**,
abolishing the **12 % slab** and introducing a 40 % demerit rate; Notification
19/2025 then omitted Schedule VII on **1 February 2026**, abolishing **28 %**
as well. Every model in this benchmark was trained on a web that is still
overwhelmingly describing the old table.

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

> Frontier models will classify goods into a **superseded** slab structure,
> emitting one of the two abolished rates — 12 % or 28 % — on a measurable
> share of items, and will do so with no drop in stated confidence.

Two abolition dates make the probe sharper than one. A model emitting `12` is
reciting a table that died in September 2025; one emitting `28` is stale in a
different way, and the leaderboard reports them separately.

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
- **Two sources, chosen for different strata:**

  | Source | Supplies | Why |
  |---|---|---|
  | Open Food Facts (India) | `typical` | Real packaged-goods listings, short and messy, ODbL-licensed |
  | GST Advance Rulings | `hard`, `adversarial`, `long_context` | Genuine classification disputes across the whole tariff — "does a quartz slab that is 92% crushed quartz and 8% resin fall under 6802 or 6810?" — with the applicant's rejected contention left in as a distractor |

- **Labelled by hand, against the primary notification.** Every judgement in
  `golden.jsonl` was made by a human. Each row records `labelled_by`, and the
  validator refuses any row that has not been.

- **Model assistance, disclosed.** A model first pass was run over the rulings
  whose operative holding was the abolished 12% slab. It proposes **no slab at
  all** — deriving
  one needs Notification 9/2025, and a model's priors are the pre-2025 table,
  which is the very error this benchmark measures. It proposes only the HSN
  heading, read out of the authority's own operative ruling in the same
  document, and it is right about that for 20 of 32.

  Those suggestions live in `data/first_pass.jsonl`, never in the golden set.
  They are marked `labelled_by: "model-first-pass"`, which
  `harness/schema.py` rejects outright — concatenating the two files fails
  validation rather than silently laundering an unreviewed label. A suggestion
  becomes an example only after a human reviews it, at which point it is
  rewritten as `human-reviewed`, and the quarantine file is left intact as the
  record of what was proposed.
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
| `answerable` | **Exact match**, reported as abstention precision/recall/F1 | Binary. |
| `justification` | **LLM-as-judge** | Genuinely open-ended — the only place a judge is warranted. |

A benchmark that judges everything with an LLM has reached for the fashionable
tool. Three of the four fields here never touch a judge, and they are
implemented in `harness/scorers/exact.py` — no model is involved in any of them.

**Stale-slab rate is scored separately**, not folded into accuracy, and is
broken down by which abolished rate was quoted. "Wrong" and "reciting a
schedule that no longer exists" are different failures, and only the second is
the finding.

**Failed and unparseable responses score as wrong**, never as skipped.
Dropping them would inflate accuracy for whichever model errors most.

**One prompt for every model** (`harness/prompt.py`, versioned). A separately
reported second pass gives each model a lightly tuned prompt; the gap between
the two passes is itself a result.

### Judge calibration

The judge scores one field — `justification` — and asks one question: **did the
model reach its answer by a route that would generalise?** That is not "was the
answer right". The rubric fails a right answer reached by a route that gets the
next example wrong, fails reasoning resting on a superseded notification, and
explicitly protects sound reasoning that is tersely or oddly worded.

```bash
python -m harness.calibration.judge_calibration --verdicts <file>
```

The report gives Cohen's κ, the confusion matrix, the **direction** of error
(too lenient vs too strict — different problems with different fixes), and
**every disagreement listed in full** with the goods, the gold answer, the
explanation and both verdicts. Categories are *suggested*, never assigned: a
model grading its own failure modes is circular, so the categorisation is the
annotator's and it is the finding.

κ is reported whatever it comes out at, and the report says so in its own words
when the judge is unusable. κ is computed by the same function as the human
self-agreement check, so the judge is held to exactly the measure the annotator
was — a test pins that they are literally the same function.

| κ | Reading |
|---|---|
| < 0.40 | Judge is unusable. Fix the rubric. |
| 0.40–0.60 | Moderate. Usable with caveats, stated. |
| 0.60–0.80 | Substantial. A good result. |
| > 0.80 | Strong — check the task has not been made trivially easy. |

**The rubric is v1 and provisional**, written before any disagreement data
existed — which is the wrong order, and the calibration report exists to
correct it. `RUBRIC_VERSION` is stamped on every verdict so a κ figure can
always be traced to the rubric that produced it.

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

Python 3.11+. Labelling, validation and self-agreement need **no dependencies** —
they run on a fresh clone before any `pip install`.

```bash
make validate    # schema + composition checks on the golden set
make test        # unit tests
make label       # interactive labelling
```

Rebuilding the corpus needs `pypdf`, because advance rulings are published as
PDFs:

```bash
pip install -e ".[collect]" && make collect
```

Model runs (week 4 onward) need API keys; copy `.env.example` to `.env`.

---

## Limitations

Written honestly, and expanded as the work proceeds.

- **Single annotator.** Self-agreement bounds this dataset, but it cannot detect
  a mistake made consistently. A second annotator would; there isn't one.
- **The judge may share a family with a benchmarked model.** Where it does, a
  self-preference effect cannot be ruled out from κ alone. The judge model is
  recorded on every run so the overlap is visible rather than implicit.
- **Ground truth has a shelf life.** GST notifications are amended. Labels are
  correct as of the date in `data/reference/rate_schedule.md` and no longer.
- **Alcohol is the only excluded family.** Alcoholic liquor for human
  consumption is outside GST by constitutional exclusion, so it has no slab to
  predict. Cement, aerated drinks, tobacco and pan masala were all excluded
  early on the mistaken premise that Schedule VII's fate was unknown; reading
  the Gazette settled every one, and all are now in scope. For tobacco, note
  that the separate excise duty introduced alongside the 40 % rate is a
  different levy and does not change which GST slab applies.
- **Source skew.** Open Food Facts is packaged food, concentrating that half of
  the corpus in Chapters 1–24. Advance rulings spread across the tariff and
  correct much of this, but the two sources differ in register as well as
  subject: a listing is a dozen words, a ruling excerpt is several hundred. A
  model's score is therefore partly a score on input length, and per-source
  results are reported separately for that reason.
- **Descriptions are reassembled** from catalogue fields (brand, name, quantity,
  packaging), which is tidier than a real marketplace listing. Concatenation
  only — no text is generated — but it is not identical to production input.
- **Advance rulings are survivorship-biased.** A dispute only reaches an
  authority when the classification was contentious, so this slice is harder
  than the population of goods a real system meets. It is not a random sample
  and is not presented as one.
- **Roughly three quarters of ruling PDFs are scans** with no text layer and are
  skipped, and files above 1.5 MB are skipped before download as probable scans.
  Both filters bias the ruling slice toward authorities that publish digitally —
  Tamil Nadu, Gujarat, West Bengal and Karnataka are over-represented relative
  to their share of rulings.

  Measured across 158 index pages (150–307): **1,580 rows → 456
  classification-of-goods rulings → 92 usable excerpts**. The attrition is
  almost entirely scans (243) plus rulings with no locatable facts section (54),
  with smaller losses to oversized files, withdrawn applications and duplicates.
  Recovering oversized files yielded only 4 usable rulings from 14 downloaded,
  which is the evidence for skipping them: oversized really does mean scanned.

  Pages 0–149 hold newer rulings and are far worse — a sample showed 27 of 28
  classification rulings were scans, against roughly half in the older range —
  so the practical ceiling is close to the 92 already collected. The ruling
  sources therefore cannot fill `hard`, `long_context` and `adversarial` alone.
  Open Food Facts supplies the remainder of `hard` through
  pre-packaged-and-labelled conditionality, and most of `out_of_scope` through
  listings too vague to classify.
- **Ruling excerpts are cut by pattern matching**, not by understanding. The
  segmenter stops before the authority's findings so the answer cannot leak, and
  refuses to emit anything when it cannot locate the facts section — but it can
  still start a few sentences early or late.
- **Goods only.** Services are out of scope, and are filtered out of the ruling
  stream because CGST s.97(2)(a) covers "goods **or services** or both".

---

## Licence

Code: MIT — see [`LICENSE`](LICENSE).
Dataset: **ODbL 1.0**, being a derived database of Open Food Facts.
Provenance for every example: [`data/DATA_LICENCE.md`](data/DATA_LICENCE.md).

> Contains information from Open Food Facts, made available under the
> [Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/).
