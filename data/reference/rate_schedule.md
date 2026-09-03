# GST Rate Schedule Reference — as in force from 22 September 2025

**Status:** v0.9 draft. Structure confirmed; individual entries still to be
checked line-by-line against the primary Gazette text before the dataset is
frozen (see [Verification checklist](#verification-checklist)).

This file is the *only* authority an annotator may consult when assigning a
slab. If a product cannot be placed using this file plus the Customs Tariff
headings, the example is `UNANSWERABLE` — it is never resolved by intuition,
by a search engine, or by asking a model.

---

## 1. The governing notifications

| Notification | Dated | In force from | Supersedes | Covers |
|---|---|---|---|---|
| **9/2025–Central Tax (Rate)** | 17 Sep 2025 | 22 Sep 2025 | 1/2017–CT(R) of 28 Jun 2017 | Rated goods, Schedules I–VII |
| **10/2025–Central Tax (Rate)** | 17 Sep 2025 | 22 Sep 2025 | 2/2017–CT(R) of 28 Jun 2017 | Exempt (nil-rated) goods |

Parallel IGST and UTGST notifications were issued the same day. This benchmark
labels the **combined GST rate** (CGST + SGST, equivalently the IGST rate), so
the CGST figures in the notification are doubled throughout.

These notifications implement the decisions of the **56th GST Council meeting
(3 September 2025)**, commonly called *GST 2.0*.

---

## 2. Label space

Notification 9/2025 lays out seven schedules. Doubling the CGST rate gives the
combined GST rate that this benchmark uses as its label:

| Schedule | CGST | **Combined GST (the label)** | Broad coverage |
|---|---|---|---|
| I | 2.5 % | **5 %** | Essential and mass-consumption goods |
| II | 9 % | **18 %** | Standard rate — the residual for most goods |
| III | 20 % | **40 %** | Demerit and luxury goods |
| IV | 1.5 % | **3 %** | Precious metals (gold, silver, platinum) |
| V | 0.125 % | **0.25 %** | Rough / unworked precious stones |
| VI | 0.75 % | **1.5 %** | Cut and polished diamonds |
| VII | 14 % | **28 %** | Narrow residual — see caution below |

Plus, from Notification 10/2025:

| Source | **Combined GST (the label)** | Coverage |
|---|---|---|
| Notification 10/2025 Schedule | **0 %** | Exempt goods |

### Permitted label values

```
0    0.25    1.5    3    5    18    28    40    UNANSWERABLE
```

### ⚠ 12 % is abolished

The 6 % CGST schedule of the old Notification 1/2017 has **no successor** in
Notification 9/2025. **`12` is not a valid label.** Items formerly at 12 %
were redistributed, predominantly to 5 %.

This matters far beyond bookkeeping. It is the benchmark's primary probe of
stale parametric knowledge: a model that emits `12` is reciting a rate table
that ceased to exist on 22 September 2025. The harness scores this separately
as the **stale-slab rate** (see `harness/scorers/`), and it is reported as a
first-class column on the leaderboard, not folded into plain accuracy.

### ⚠ Caution on Schedule VII (28 %)

Secondary commentary places tobacco, pan masala, aerated beverages and certain
cement in Schedule VII at 14 % CGST / 28 % GST. There is a known transitional
question here: several demerit items were widely reported as remaining at
28 % + compensation cess until the cess loan obligations were discharged,
moving to the 40 % Schedule III rate thereafter.

**Consequence for labelling:** any product falling in the tobacco / pan masala /
aerated-beverage / cement families is treated as **out of scope for v1.0** and
excluded from the golden set, unless and until the transitional position is
confirmed against the primary text and any subsequent amending notification.
An unstable ground truth is worse than a smaller dataset.

---

## 3. Ordered lookup procedure

Annotators apply these steps **in order** and stop at the first that resolves.
Following a fixed procedure rather than judgement is what makes the
self-agreement check meaningful.

1. **Fix the essential character** of the good from the description alone.
   If this fails → `UNANSWERABLE`.
2. **Assign the HSN heading** (4-digit) using the Customs Tariff and the
   General Rules of Interpretation (GRI 1 → 3(a) → 3(b) → 3(c)).
3. **Check Notification 10/2025** (exemptions). If listed → `0`.
4. **Check Notification 9/2025** Schedules I–VII. First matching entry wins.
5. **Apply conditionality tests** (§4 of `../guideline.md`) — most importantly
   *pre-packaged and labelled*, which can move a food item between `0` and `5`.
6. **Residual.** A good not covered by any specific entry falls to the
   Schedule II standard rate → `18`.
7. If the rate turns on a fact the description does not state → `UNANSWERABLE`.

---

## 4. Primary sources

| Document | Where |
|---|---|
| CBIC GST rate finder (official portal) | <https://taxinformation.cbic.gov.in/> |
| CBIC GST rates landing page | <https://cbic-gst.gov.in/gst-goods-services-rates.html> |
| Notification 10/2025–CT(R), Gazette text (PDF) | <https://taxo.online/wp-content/uploads/2025/09/NN-10-2025_CT_R.pdf> |

Secondary commentary was used to establish the *structure* of the schedules
during drafting. No secondary source is permitted as the authority for an
individual example's label.

---

## Verification checklist

Blocking items — all must be cleared before `golden.jsonl` is tagged v1.0.

- [ ] Download the Gazette PDFs of Notification 9/2025 and 10/2025 into
      `data/reference/primary/` and record their SHA-256 hashes.
- [ ] Confirm Schedule VII's scope and the tobacco / aerated-beverage
      transitional position; either bring those families in scope or record
      the exclusion in `../guideline.md` §7.
- [ ] Confirm no 6 % CGST schedule exists (i.e. `12` really is unavailable).
- [ ] Check for amending notifications issued **after** 17 September 2025 that
      alter any entry relied upon. Record the date this check was last run.
- [ ] Re-verify every rate asserted in the five worked examples of
      `../guideline.md` against the primary text.

**Last checked against primary sources:** _not yet — draft built from the
notification structure only._
