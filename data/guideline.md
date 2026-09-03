# Annotation Guideline — Indian GST Rate-Slab Classification

**Version 0.9 (draft)** · Task frozen, rate table pending primary-source
verification · Maintainer: Ardhendu Debnath

Read this in full before labelling. Re-read §4 and §5 at the start of every
batch — they are where nearly all self-disagreement comes from.

---

## 1. The task

Given a **real product description**, exactly as it appears in a catalogue,
listing or ruling, decide the GST rate that applies to a supply of that good in
India today.

The annotator records four fields:

| Field | Type | Meaning |
|---|---|---|
| `slab` | one of `0`, `0.25`, `1.5`, `3`, `5`, `18`, `28`, `40`, `UNANSWERABLE` | The combined GST rate |
| `hsn4` | 4-digit string, or `null` | The HSN heading that fixes the rate |
| `answerable` | boolean | `false` iff `slab` is `UNANSWERABLE` |
| `justification` | short prose | Which schedule entry, and why this heading |

`slab` and `hsn4` are scored deterministically. `justification` is the only
field that needs an LLM judge — which is why it exists as a separate field
rather than being mixed into the answer.

**Scope.** Goods only. Services (Chapter 99) are out of scope for v1.0.

---

## 2. Where the answer comes from

The single authority is [`reference/rate_schedule.md`](reference/rate_schedule.md),
which digests **Notification 9/2025–CT(Rate)** and **Notification 10/2025–CT(Rate)**,
both in force from **22 September 2025**.

Three rules, and they are absolute:

1. **Never label from memory.** Rates changed substantially on 22 Sep 2025.
   Anything you half-remember is probably the old table.
2. **Never label from a search engine result or an LLM.** Blogs disagree with
   each other and with the Gazette. If it is not in the reference file or the
   primary notification, it is not a label — it is a guess.
3. **`12` is not a valid label.** The 12 % slab was abolished. If you find
   yourself reaching for it, you have slipped into the pre-2025 table.

### 2a. Examples drawn from advance rulings — read this before labelling one

Examples with `source: "aar"` come from published Advance Ruling orders. They
carry metadata that is genuinely useful *and* actively dangerous, so treat the
two halves differently:

| Field | Status | Use it? |
|---|---|---|
| `hsn_candidates` | Codes the ruling discusses. HSN is the Customs Tariff, which GST 2.0 did not touch, so these remain valid | **Yes** — as a research hint |
| `ruling_brief` | The Council's summary of the question, sometimes naming the outcome | **Yes** — for the heading |
| `stale_rates_in_ruling` | Rates **as stated in the ruling** | **Never** — see below |
| `ruling_url` | Link to the full order | Yes, when the excerpt is unclear |

**The trap.** Most published rulings predate 22 September 2025. Any rate they
state comes from the superseded schedule. A ruling that concludes "taxable at
12 %" was correct when written and is wrong today, because the 12 % slab no
longer exists.

So: **take the heading from the ruling, derive the slab yourself.** Run the HSN
through step 3 and step 4 of the procedure against Notification 9/2025 exactly
as you would for any other example.

**Turn the trap into a resource.** A ruling whose `stale_rates_in_ruling`
contains `12` is, by construction, an example whose rate moved — the slab it
sat in was abolished. These are the cheapest way to fill the
`rate-changed-2025` slice that the headline finding depends on, so tag them and
prioritise them.

**Adversarial content is deliberate.** The excerpt stops before the authority's
findings, but it *keeps* the applicant's own contention — and applicants argue
for the classification that suits them, which the authority then frequently
rejects. An excerpt reading "the applicant submits the goods merit
classification under tariff item 1207 40 90" is not telling you the answer; it
may be telling you the wrong answer. Label these `adversarial` and record in
`labeller_notes` whether you agreed with the applicant.

---

## 3. The ordered procedure

Apply in order. Stop at the first step that resolves. Do not skip ahead
because the answer "feels obvious" — the fixed order is what makes your
self-agreement measurable.

```
1. Fix the essential character of the good from the description alone.
   └─ cannot? → UNANSWERABLE (reason: "no product kind")

2. Assign the 4-digit HSN heading (GRI 1 → 3(a) → 3(b) → 3(c)).

3. Listed in Notification 10/2025 (exemptions)?          → slab 0

4. Listed in Notification 9/2025, Schedules I–VII?       → that schedule's rate
   (first matching entry wins)

5. Apply the conditionality tests in §4.

6. Not covered by any specific entry?                    → slab 18 (residual)

7. Does the rate turn on a fact the description omits?
   └─ yes → UNANSWERABLE (reason: "rate-determining fact absent")
```

Record which step resolved the example in `labeller_notes`. This makes
disagreements diagnosable later instead of mysterious.

---

## 4. Conditionality tests

These are where the task is genuinely hard, and where a careless annotator
disagrees with themselves a week later.

### 4a. Pre-packaged and labelled

Since July 2022 the branded-versus-unbranded distinction has been replaced by
whether the good is *pre-packaged and labelled* within the meaning of the Legal
Metrology Act. For many staple foods this is the difference between `0` and `5`.

**Operational test — treat the good as pre-packaged and labelled if the
description shows any of:**

- a declared net quantity (`1 kg`, `500 g`, `5 L`), **and** a brand name; or
- explicit packaging words: `pouch`, `packet`, `sealed pack`, `carton`, `tetra pak`; or
- an MRP.

**Treat as loose / not pre-packaged if the description says** `loose`, `unpackaged`,
`sold by weight`, `bulk`, or gives a quantity with no brand and no packaging word.

If neither test fires cleanly → `UNANSWERABLE` (reason: "packaging status
indeterminate"). Do not default to one or the other.

### 4b. Sets and composite goods (GRI 3)

For a set of goods carrying different rates:

- **GRI 3(a)** — a heading giving the most specific description beats a general one.
- **GRI 3(b)** — if one component gives the set its *essential character*, the whole
  set takes that component's rate.
- **GRI 3(c)** — if no component dominates, take the heading occurring **last in
  numerical order** among those equally meriting consideration.

Always record which limb you used in `justification`. "GRI 3(c)" is a real
answer; "it's a gift set so 18 %" is not.

### 4c. Parts and accessories

A part is not automatically rated as the machine it belongs to. Follow the
Section and Chapter Notes for the relevant Section. If the description does not
make clear whether the item is the good itself or a part of it →
`UNANSWERABLE`.

### 4d. Out-of-scope families for v1.0

Do **not** label products in these families; they are dropped at collection time
by `harness.schema.out_of_scope_term`.

**Excluded because the rate is unsettled** — the transitional position of
Schedule VII / 40 % is not confirmed (see `reference/rate_schedule.md`):

- tobacco, cigarettes, bidis, pan masala, gutkha
- aerated, carbonated and energy drinks
- cement

**Excluded because there is no GST rate to predict** — alcoholic liquor for
human consumption is outside GST by constitutional exclusion and is taxed under
state excise:

- beer, wine, spirits and other alcoholic liquor

**Excluded by scope:** services (Chapter 99).

A label that may be wrong for reasons outside the annotator's control
contaminates the ceiling for every model. Screening happens against the product
*category* as well as the description, because a listing reading
`"Thums up, 250 ml"` never contains the word "carbonated".

---

## 5. When to mark `UNANSWERABLE`

This is the **10 % stratum**, and it is the most valuable part of the dataset.
Production systems fail by answering confidently when they should decline;
almost no benchmark measures it. This one does.

Mark `UNANSWERABLE` when — and only when — one of these holds:

| Reason code | Condition | Example description |
|---|---|---|
| `no-product-kind` | No noun identifying what the good *is* | `"Combo Pack of 3 — Assorted"` |
| `model-number-only` | Brand and model, no product category | `"Havells XR-2000 Pro"` |
| `rate-fact-absent` | Rate turns on a stated-nowhere fact | `"Royal Enfield motorcycle, black"` (engine cc unstated) |
| `packaging-indeterminate` | §4a fires neither way | `"Wheat flour 1 kg"` (no brand, no packaging word) |
| `multi-good-no-dominant` | Several goods, GRI 3 cannot resolve | genuinely irreducible bundles |

**Not** grounds for `UNANSWERABLE`:

- the description is merely long, messy, or badly spelled;
- you personally do not know the rate (→ look it up in the reference);
- the good is unusual (→ residual `18` under step 6).

A correct `UNANSWERABLE` is a *positive* label with a reason code, not a
shrug. Always fill `labeller_notes` with the specific missing fact.

---

## 6. Five worked examples

> ⚠ The rates asserted below are drafted from the schedule structure and are on
> the verification checklist in `reference/rate_schedule.md`. Re-confirm each
> against the Gazette text before the v1.0 freeze.

### WE-1 — typical

**Input:** `Tata Salt Iodised Free Flowing, 1 kg pouch`

- Step 1: essential character — edible common salt.
- Step 2: heading **2501**.
- Step 3: salt appears in the Notification 10/2025 exemption schedule → resolved.

```
slab = 0 · hsn4 = "2501" · answerable = true
justification: "Common edible salt, HSN 2501, exempt under Notification
10/2025-CT(R). Exemption is unconditional, so the 1 kg branded pouch does not
attract the pre-packaged test."
difficulty = typical
```

*Teaching point:* step 3 precedes the conditionality tests. Reaching for §4a
here is a common early mistake.

### WE-2 — typical, and a rate that moved

**Input:** `Colgate Strong Teeth Toothpaste 200g`

- Step 2: heading **3306** (dentifrices).
- Step 4: dentifrices sit in Schedule I under GST 2.0.

```
slab = 5 · hsn4 = "3306" · answerable = true
justification: "Dentifrice, HSN 3306, Notification 9/2025 Schedule I (2.5% CGST
+ 2.5% SGST). Rated 18% before 22 Sep 2025."
difficulty = typical · tags = ["rate-changed-2025"]
```

*Teaching point:* tag every example whose rate moved on 22 Sep 2025. These form
the slice that exposes stale model knowledge, and the harness reports accuracy
on this slice separately.

### WE-3 — hard, conditionality

**Input:** `Aashirvaad Whole Wheat Atta, 5 kg pack`

- Step 2: heading **1101** (wheat flour).
- Step 3: wheat flour is exempt **only when not pre-packaged and labelled**.
- Step 5 / §4a: brand name + declared net quantity + `pack` → pre-packaged and
  labelled → the exemption does not apply; Schedule I does.

```
slab = 5 · hsn4 = "1101" · answerable = true
justification: "Wheat flour, HSN 1101. Exempt under Notification 10/2025 only
when not pre-packaged and labelled. Brand plus declared 5 kg quantity makes this
pre-packaged and labelled, so Notification 9/2025 Schedule I applies."
difficulty = hard · tags = ["conditionality", "pre-packaged"]
```

### WE-4 — **edge case**: rate-determining fact absent

**Input:** `Royal Enfield Motorcycle — Black, single owner`

- Step 2: heading **8711** (motorcycles).
- Step 4: the schedules split motorcycles at **350 cc** — at or below sits in the
  standard schedule, above it in the demerit schedule.
- Step 7: the description never states engine capacity. Royal Enfield sells
  models on both sides of the threshold, so this is not recoverable from the
  brand.

```
slab = UNANSWERABLE · hsn4 = "8711" · answerable = false
justification: "Motorcycle, HSN 8711. The applicable rate turns on engine
capacity relative to the 350 cc threshold, which the description does not state
and the brand does not imply."
difficulty = hard · tags = ["unanswerable", "rate-fact-absent"]
labeller_notes: "reason=rate-fact-absent; missing=engine_capacity_cc"
```

*Teaching point:* `hsn4` is still recorded. The heading is knowable even when
the slab is not — and separating the two lets the harness show that a model
classified the good correctly yet still should have declined.

### WE-5 — **edge case**: composite set, GRI 3(c) cascade

**Input:** `Diwali Gift Hamper — assorted dry fruits 250g, two scented candles,
decorative brass diya`

- GRI 3(a): no single heading covers the set → fails.
- GRI 3(b): dry fruits, candles and the diya are comparable in prominence; no
  component gives the set its essential character → fails.
- GRI 3(c): among headings **0802** (nuts), **3406** (candles) and **7418**
  (brass articles), take the last in numerical order → **7418**.

```
slab = 18 · hsn4 = "7418" · answerable = true
justification: "Set put up for retail sale with no component supplying the
essential character. GRI 3(b) fails; GRI 3(c) selects the heading last in
numerical order, 7418, which sits in Notification 9/2025 Schedule II."
difficulty = adversarial · tags = ["composite", "GRI-3c", "distractor"]
```

*Teaching point:* the components have **different** rates, which is exactly what
makes the set a set. Answering "18 % because gift hampers are 18 %" reaches the
right number by the wrong route — and the judge is instructed to fail it, because
the same shortcut gets the next hamper wrong.

---

## 7. Working practice

1. **Batches of 50, with a real break between them.** Fatigue produces
   inconsistency, and inconsistency lowers the ceiling on every model score.
2. **Never edit a labelled example in place.** Append a corrected row with a new
   `id` and set `deprecated_by` on the old one. Dataset drift is handled, not
   hidden.
3. **Re-label check.** One week after first labelling, re-label 50 randomly drawn
   examples without looking at the originals (`make relabel`). Agreement below
   ~85 % means this guideline is too vague — fix it and re-label the affected
   batches rather than pressing on.
4. **Record the self-agreement number in the README.** It is the ceiling against
   which every model is judged, and stating it publicly is the point.
5. **No LLM assistance in labelling.** Not for a first pass, not for
   tie-breaking. The entire value of this dataset is that a human made the
   judgements against a primary legal text.

---

## 8. Target composition

400 examples, stratified deliberately — not sampled at random:

| Share | Stratum | What it means here |
|---|---|---|
| 40 % | typical | Unambiguous single good, clear heading |
| 25 % | hard | Conditionality, sets, parts, near-threshold |
| 15 % | long-context | Full catalogue blocks and ruling extracts |
| 10 % | adversarial | Misleading brand names, distractor components |
| 10 % | out-of-scope | Correct answer is `UNANSWERABLE` |

Cross-cutting tag, tracked independently of the strata: **`rate-changed-2025`**
on every example whose rate moved on 22 September 2025. Target at least 60 such
examples so the stale-knowledge finding rests on a large enough slice to carry a
usable confidence interval.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.9 | 2026-09-03 | Initial draft. Task, label space, procedure and worked examples fixed. Rate assertions pending primary-source verification. |
