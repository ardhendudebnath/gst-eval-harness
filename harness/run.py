"""Run the benchmark. The plan's one-command reproduction.

    python -m harness.run --all            # every model in the registry
    python -m harness.run --model opus-5   # one model
    python -m harness.run --all --dry-run  # cost estimate, no API calls

Every call costs money, so `--dry-run` is offered first-class and the driver
refuses to start against an empty or unfrozen golden set — a run scored against
nothing produces a leaderboard of zeros that looks like a result.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from harness import env as env_mod
from harness import prompt as prompt_mod
from harness.report import cost as cost_mod
from harness.report.results import RunResult, dataset_fingerprint, new_run_id
from harness.runners import MODELS, RunnerError, build, get
from harness.scorers.exact import score_row, summarise
from harness.schema import Example, read_jsonl

GOLDEN = Path("data/golden.jsonl")

#: Rough per-example token cost, for the dry-run estimate only. Deliberately
#: crude and labelled as such — its job is to stop someone spending real money
#: without any idea of the bill, not to be accurate.
EST_TOKENS_IN = 700
EST_TOKENS_OUT = 250


def load_dataset(limit: int | None = None) -> list[Example]:
    rows = [e for e in read_jsonl(GOLDEN) if e.is_active]
    return rows[:limit] if limit else rows


def estimate(keys: list[str], n: int) -> None:
    print(f"\n  Dry run — {n} example(s), no API calls made.")
    print("  Estimates use a crude fixed token count; treat as an order of")
    print("  magnitude, not a quote.\n")
    total = 0.0
    for key in keys:
        spec = get(key)
        usd = spec.cost_usd(EST_TOKENS_IN * n, EST_TOKENS_OUT * n)
        priced = spec.usd_in_per_m > 0
        shown = f"${usd:,.2f}" if priced else "unpriced"
        total += usd
        print(f"    {key:<14} {spec.tier:<12} {shown}")
    print(f"\n    {'total':<14} {'':<12} ${total:,.2f}\n")


def run_one(key: str, dataset: list[Example], *, mode: str, sleep: float) -> RunResult | None:
    spec = get(key)
    try:
        runner = build(key)
    except RunnerError as exc:
        print(f"  {key}: skipped — {exc}")
        return None

    # Fingerprint the file the dataset was actually loaded from. Relying on the
    # default here would read a second module-level constant for the same path
    # — they agree today, but a run that scored one file and stamped the
    # provenance of another would be silently wrong about the thing the
    # fingerprint exists to prove.
    sha, n_rows = dataset_fingerprint(GOLDEN)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    completions, scores, rows = [], [], []

    print(f"\n  {key} ({spec.model_id}) — {len(dataset)} example(s)")
    for i, example in enumerate(dataset, 1):
        completion = runner.run(
            prompt_mod.build(example.input), system=prompt_mod.SYSTEM
        )
        parsed = prompt_mod.parse(completion.text)
        score = score_row(example, parsed, errored=not completion.ok,
                          text=completion.text)

        completions.append(completion)
        scores.append(score)
        rows.append(
            {
                "id": example.id,
                "gold_slab": example.slab,
                "predicted_slab": parsed.slab,
                "correct": score.slab_correct,
                "stale_slab": score.stale_slab,
                "stale_cited": list(score.stale_cited),
                "hsn_correct": score.hsn_correct,
                "tokens_in": completion.tokens_in,
                "tokens_out": completion.tokens_out,
                "latency_ms": completion.latency_ms,
                "error": completion.error,
            }
        )
        if i % 25 == 0 or i == len(dataset):
            acc = sum(s.slab_correct for s in scores) / len(scores)
            print(f"    {i}/{len(dataset)}  slab acc so far {acc:.1%}")
        if sleep:
            time.sleep(sleep)

    summary = summarise(scores)
    correct = sum(s.slab_correct for s in scores)
    report = cost_mod.build(spec, completions, correct)
    served = next((c.model for c in completions if c.ok), spec.model_id)

    result = RunResult(
        run_id=new_run_id(key, mode),
        model_key=key,
        model_id=spec.model_id,
        served_model_id=served,
        provider=spec.provider,
        tier=spec.tier,
        prompt_version=prompt_mod.PROMPT_VERSION,
        prompt_mode=mode,
        dataset_sha=sha,
        dataset_n=n_rows,
        started_at=started,
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        summary=summary.as_row(),
        cost=report.as_row(),
        rows=rows,
    )
    path = result.save()
    print(f"    slab {summary.slab_acc:.1%} · stale {summary.stale_slab_rate:.1%} "
          f"· errored {summary.errored} → {path}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="run every model")
    ap.add_argument("--model", action="append", default=[], help="run one model key")
    ap.add_argument("--limit", type=int, default=None, help="first N examples only")
    ap.add_argument("--mode", choices=["shared", "tuned"], default="shared")
    ap.add_argument("--sleep", type=float, default=0.0, help="pause between calls")
    ap.add_argument("--dry-run", action="store_true", help="estimate cost, call nothing")
    args = ap.parse_args()

    # Before anything asks for a key. Names only — a run log that echoed the
    # values would put them in the terminal scrollback and any pasted output.
    loaded = env_mod.load()
    if loaded:
        print(f"  .env: loaded {', '.join(sorted(loaded))}")

    keys = list(MODELS) if args.all else args.model
    if not keys:
        ap.error("choose --all or --model KEY")

    dataset = load_dataset(args.limit)
    if not dataset:
        print(
            f"\n  {GOLDEN} is empty — nothing to score against.\n"
            "  Label examples first: python -m harness.label.cli\n",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        estimate(keys, len(dataset))
        return 0

    results = [
        r for key in keys
        if (r := run_one(key, dataset, mode=args.mode, sleep=args.sleep))
    ]
    if not results:
        print("\n  no model ran — check credentials\n", file=sys.stderr)
        return 1

    from harness.report import leaderboard

    leaderboard.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
