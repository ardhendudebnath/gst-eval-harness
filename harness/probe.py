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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="open-weight")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.5)
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
    print(f"  {len(refs)} reference(s) · {spec.model_id}\n")

    scores, rows = [], []
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

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
            # The whole response, because the stale-citation metric reads it
            # and a truncated copy cannot be re-scored.
            "response": c.text,
        })
        mark = ("ok   " if s.slab_correct
                else "STALE" if s.recites_dead_schedule else "wrong")
        print(f"  {i:2d}/{len(refs)}  {ex.id}  hsn {ex.hsn4}  "
              f"gazette {ex.slab:>2}%  said {str(parsed.slab):>12}  {mark}",
              flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    summary = summarise(scores)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "NOT_THE_GOLDEN_SET": DISCLAIMER,
        "model_key": args.model,
        "model_id": spec.model_id,
        "prompt_version": prompt_mod.PROMPT_VERSION,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary.as_row(),
        "rows": rows,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n" + "=" * 64)
    print(f"  n                     {summary.n}")
    print(f"  slab accuracy         {summary.slab_acc:.1%}")
    print(f"  hsn-4 accuracy        {summary.hsn_acc:.1%}")
    print(f"  stale slab ANSWERED   {summary.stale_slab_rate:.1%}  "
          f"{summary.stale_by_slab}")
    print(f"  stale slab RECITED    {summary.stale_cited_rate:.1%}  "
          f"{summary.stale_cited_by_slab}   <- includes refusals")
    print(f"  errored {summary.errored}   unparseable {summary.unparseable}")
    print(f"  {describe_stale(summary)}")
    print("=" * 64)
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
