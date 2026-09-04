"""Score a model against slabs read out of the archived Gazette.

    python -m harness.probe --model open-weight

**This is not the benchmark.** `data/golden.jsonl` is the benchmark, it is
built by human review, and `harness.run` is what scores against it. This module
exists because that file does not exist yet, and a harness with no measurement
at all cannot be debugged, tuned, or argued with.

What it scores against: the first-pass suggestions whose slab resolved to
exactly one entry in `data/reference/primary/`. That reference is a document
lookup rather than a model's opinion, so scoring against it is not circular.

What is wrong with it, stated plainly because the README cites these numbers:

  * The HSN heading came from each authority's operative ruling by automated
    extraction. Nobody has checked those mappings one by one. A heading
    extracted wrongly makes the reference wrong with it.
  * The set is whatever happened to resolve unambiguously, so it is skewed --
    heavily 18%, heavily one state, and almost free of the rate-changed goods
    the project's hypothesis is actually about.
  * It therefore measures the harness, and gives an order of magnitude for the
    model. It does not establish anything about Indian GST.

Output goes to `results/gazette_probe.json`, whose first field says all of the
above, and which the leaderboard does not read.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from harness import env as env_mod
from harness import prompt as prompt_mod
from harness.runners import RunnerError, build
from harness.runners.registry import get
from harness.schema import Example
from harness.scorers.exact import describe_stale, score_row, summarise

FIRST_PASS = Path("data/first_pass.jsonl")
OUT = Path("results/gazette_probe.json")

DISCLAIMER = (
    "NOT THE GOLDEN SET. The reference is data/first_pass.jsonl slabs read from "
    "the archived Gazette, not human-reviewed labels. data/golden.jsonl does not "
    "exist. HSN headings were extracted automatically and are unaudited. The "
    "leaderboard does not read this file. See harness/probe.py."
)


def references() -> list[tuple[Example, dict]]:
    """The suggestions whose slab resolved to exactly one Gazette entry."""
    out = []
    for line in FIRST_PASS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["slab"] == "UNCERTAIN" or not r["hsn4"]:
            continue
        out.append((
            Example(
                id=r["id"], input=r["input"], slab=r["slab"], hsn4=r["hsn4"],
                answerable=r.get("answerable", True),
                justification=r.get("justification") or "",
                difficulty="typical", source=r.get("source", "aar"),
            ),
            r,
        ))
    return out


def aggregate(runs: list[dict], refs: list[tuple[Example, dict]]) -> dict:
    """Mean and range per metric, plus how much the model agrees with itself.

    A single run of this probe was shown to carry run-to-run noise the same
    size as the finding it reports, so a lone figure is not a measurement. The
    spread is reported next to the mean, always.
    """
    metrics = ("slab_acc", "hsn_acc", "stale_slab_rate", "stale_cited_rate",
               "abstention_acc")
    spread = {}
    for m in metrics:
        vals = [r["summary"][m] for r in runs]
        spread[m] = {
            "mean": round(sum(vals) / len(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "range": round(max(vals) - min(vals), 4),
            "runs": [round(v, 4) for v in vals],
        }

    # Per-example stability: the same prompt, the same model, N times.
    by_id: dict[str, list] = {}
    for r in runs:
        for row in r["rows"]:
            by_id.setdefault(row["id"], []).append(row["predicted_slab"])

    gold = {ex.id: ex.slab for ex, _ in refs}
    unstable, majority_correct = [], 0
    for eid, answers in by_id.items():
        distinct = {str(a) for a in answers}
        if len(distinct) > 1:
            unstable.append({"id": eid, "gazette": gold.get(eid),
                             "answers": answers})
        top = Counter(str(a) for a in answers).most_common(1)[0][0]
        if top == gold.get(eid):
            majority_correct += 1

    return {
        "runs": len(runs),
        "metrics": spread,
        "self_agreement": {
            "examples": len(by_id),
            "answered_identically_every_run": len(by_id) - len(unstable),
            "unstable": len(unstable),
            "rate": round((len(by_id) - len(unstable)) / len(by_id), 4) if by_id else 0.0,
            "detail": unstable,
        },
        # Does asking repeatedly and taking the plurality beat asking once?
        "majority_vote_slab_acc": round(majority_correct / len(by_id), 4) if by_id else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="open-weight")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--repeats", type=int, default=1,
                    help="run the whole set N times and report mean and range")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    loaded = env_mod.load()
    if loaded:
        print(f"  .env: loaded {', '.join(sorted(loaded))}")

    refs = references()[: args.limit]
    if not refs:
        print(f"\n  nothing grounded in {FIRST_PASS}\n")
        return 1

    spec = get(args.model)
    try:
        runner = build(args.model)
    except RunnerError as exc:
        print(f"\n  {args.model}: {exc}\n")
        return 1

    print(f"\n  {DISCLAIMER}\n")
    print(f"  {len(refs)} reference(s) × {args.repeats} run(s) · {spec.model_id}\n")

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    runs = []

    for attempt in range(1, args.repeats + 1):
        scores, rows = [], []
        for i, (ex, src) in enumerate(refs, 1):
            c = runner.run(prompt_mod.build(ex.input), system=prompt_mod.SYSTEM)
            parsed = prompt_mod.parse(c.text)
            s = score_row(ex, parsed, errored=not c.ok, text=c.text)
            scores.append(s)
            rows.append({
                "id": ex.id, "hsn4": ex.hsn4,
                "gazette_slab": ex.slab, "predicted_slab": parsed.slab,
                "correct": s.slab_correct,
                "stale_slab": s.stale_slab,
                "stale_cited": list(s.stale_cited),
                "predicted_hsn": parsed.hsn4, "hsn_correct": s.hsn_correct,
                "state": (src.get("collection_meta") or {}).get("state", "?"),
                "tokens_in": c.tokens_in, "tokens_out": c.tokens_out,
                "reasoning_chars": c.extra.get("reasoning_chars", 0),
                "error": c.error,
                # The whole response, because the stale-citation metric reads
                # it and a truncated copy cannot be re-scored.
                "response": c.text,
            })
            mark = ("ok   " if s.slab_correct
                    else "STALE" if s.recites_dead_schedule else "wrong")
            print(f"  run {attempt}  {i:2d}/{len(refs)}  {ex.id}  hsn {ex.hsn4}  "
                  f"gazette {ex.slab:>2}%  said {str(parsed.slab):>12}  {mark}",
                  flush=True)
            if args.sleep:
                time.sleep(args.sleep)

        summary = summarise(scores)
        runs.append({"run": attempt, "summary": summary.as_row(), "rows": rows})
        print(f"  --- run {attempt}: slab {summary.slab_acc:.1%} · "
              f"answered {summary.stale_slab_rate:.1%} · "
              f"recited {summary.stale_cited_rate:.1%} ---\n", flush=True)

    agg = aggregate(runs, refs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "NOT_THE_GOLDEN_SET": DISCLAIMER,
        "model_key": args.model,
        "model_id": spec.model_id,
        "prompt_version": prompt_mod.PROMPT_VERSION,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # The last run's summary, so single-run consumers keep working. The
        # aggregate is what should actually be quoted.
        "summary": runs[-1]["summary"],
        "rows": runs[-1]["rows"],
        "aggregate": agg,
        "all_runs": [{"run": r["run"], "summary": r["summary"]} for r in runs],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=" * 70)
    print(f"  {len(refs)} examples × {agg['runs']} run(s)\n")
    print(f"  {'metric':<24}{'mean':>8}{'min':>8}{'max':>8}{'range':>8}")
    for name, d in agg["metrics"].items():
        print(f"  {name:<24}{d['mean']:>8.1%}{d['min']:>8.1%}"
              f"{d['max']:>8.1%}{d['range']:>8.1%}")
    sa = agg["self_agreement"]
    print(f"\n  same answer every run : {sa['answered_identically_every_run']}"
          f"/{sa['examples']}  ({sa['rate']:.1%})")
    print(f"  majority-vote slab acc: {agg['majority_vote_slab_acc']:.1%}")
    if sa["detail"]:
        print("\n  examples the model could not answer the same way twice:")
        for d in sa["detail"]:
            print(f"    {d['id']}  gazette {str(d['gazette']):>4}%  "
                  f"answers {d['answers']}")
    print("=" * 70)
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
