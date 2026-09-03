"""Render the leaderboard to a static HTML file.

    python -m harness.report.leaderboard

Design decisions the numbers force:

  * **Ranked by cost per correct answer, not accuracy.** That is the metric the
    project exists to publish, and it reorders leaderboards. Accuracy is still
    shown, first, because it is what a reader looks for.
  * **Stale-slab is a column, not a footnote.** It is the finding.
  * **A stale dataset fingerprint is shown as a warning on the row**, not
    silently ranked alongside fresh runs.
  * **An empty leaderboard says so.** A table of zeros would imply models were
    run and scored badly; no model has been called at all.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from harness.report.results import RunResult, dataset_fingerprint, latest_per_model, load_all
from harness.runners.registry import FX_READ_ON, PRICES_READ_ON

OUT = Path("results/leaderboard.html")


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _money(value, prefix) -> str:
    if value is None:
        return "—"
    return f"{prefix}{value:,.4f}" if value < 1 else f"{prefix}{value:,.2f}"


def _rank(runs: list[RunResult]) -> list[RunResult]:
    """Cheapest correct answer first; unpriced runs last, in accuracy order."""

    def key(run: RunResult):
        cost = run.cost.get("inr_per_correct")
        acc = run.summary.get("slab_acc", 0)
        return (0, cost, -acc) if cost is not None else (1, 0.0, -acc)

    return sorted(runs, key=key)


def render(runs: list[RunResult], current_sha: str, current_n: int) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ranked = _rank(runs)

    if not ranked:
        body = (
            '<p class="empty"><strong>No model has been run yet.</strong> '
            "This table is empty because the harness has never called an API — "
            "not because models scored zero. It fills in when "
            "<code>python -m harness.run --all</code> completes against a "
            "labelled golden set.</p>"
        )
    else:
        rows = []
        for run in ranked:
            s, c = run.summary, run.cost
            stale_bits = " ".join(
                f'<span class="dead">{html.escape(k)}%×{v}</span>'
                for k, v in (s.get("stale_by_slab") or {}).items()
            )
            drift = ""
            if current_sha and run.dataset_sha and run.dataset_sha != current_sha:
                drift = (
                    ' <span class="warn" title="scored against an older golden set">'
                    "stale dataset</span>"
                )
            rows.append(
                "<tr>"
                f'<td class="model"><b>{html.escape(run.model_key)}</b>'
                f'<span class="mid">{html.escape(run.served_model_id or run.model_id)}</span></td>'
                f'<td class="tier">{html.escape(run.tier)}</td>'
                f"<td>{_pct(s.get('slab_acc'))}</td>"
                f"<td>{_pct(s.get('hsn_acc'))}</td>"
                f"<td>{_pct(s.get('abstain_f1'))}</td>"
                f'<td class="stale">{_pct(s.get("stale_slab_rate"))} {stale_bits}</td>'
                f"<td>{_money(c.get('inr_per_correct'), '₹')}</td>"
                f"<td>{_money(c.get('usd_total'), '$')}</td>"
                f"<td>{c.get('p50_latency_ms', 0):,} ms</td>"
                f'<td class="when">{html.escape(run.run_date)}{drift}</td>'
                "</tr>"
            )
        body = (
            "<table><thead><tr>"
            "<th>Model</th><th>Tier</th><th>Slab acc.</th><th>HSN-4</th>"
            "<th>Abstain F1</th><th>Stale-slab</th><th>₹ / correct</th>"
            "<th>Run cost</th><th>p50</th><th>Run date</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    ceiling = (
        f"Human self-agreement ceiling: not yet measured. "
        f"Golden set: {current_n} rows."
        if current_n
        else "Golden set is empty — no ceiling, and nothing to score against."
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GST rate-slab leaderboard</title>
<style>
:root {{
  --bg:#eef1f3; --card:#f8fafb; --rule:#c6d0d5; --ink:#101a1f;
  --soft:#4a5c65; --faint:#7d8f98; --accent:#0d6a6d; --warn:#b06a12;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0b1114; --card:#111a1e; --rule:#24343a; --ink:#e4edf0;
    --soft:#9db0b8; --faint:#6b8089; --accent:#4fd0cd; --warn:#e8a33f;
  }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.6 "IBM Plex Sans",ui-sans-serif,system-ui,sans-serif; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:36px 22px 60px; }}
h1 {{ font-size:1.7rem; margin:0 0 4px; letter-spacing:-.01em; }}
.sub {{ color:var(--soft); margin:0 0 22px; max-width:62ch; }}
.scroll {{ overflow-x:auto; border:1px solid var(--rule); border-radius:3px;
  background:var(--card); }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th,td {{ padding:9px 12px; text-align:right; white-space:nowrap;
  border-bottom:1px solid var(--rule); }}
th {{ font-size:.7rem; letter-spacing:.08em; text-transform:uppercase;
  color:var(--faint); font-weight:500; text-align:right; }}
th:first-child, td:first-child, .tier, .when {{ text-align:left; }}
tbody tr:last-child td {{ border-bottom:none; }}
.model b {{ display:block; }}
.mid, .when {{ font:400 .72rem/1.5 "IBM Plex Mono",ui-monospace,monospace;
  color:var(--faint); }}
.tier {{ color:var(--soft); }}
.stale .dead {{ font:400 .72rem "IBM Plex Mono",monospace; color:var(--warn);
  margin-left:5px; }}
.warn {{ color:var(--warn); }}
.empty {{ background:var(--card); border:1px solid var(--rule);
  border-left:3px solid var(--accent); border-radius:2px; padding:16px 18px;
  margin:0; }}
.notes {{ margin-top:26px; color:var(--soft); font-size:.86rem; max-width:70ch; }}
.notes li {{ margin-bottom:6px; }}
code {{ font-family:"IBM Plex Mono",monospace; font-size:.85em; }}
footer {{ margin-top:28px; padding-top:14px; border-top:1px solid var(--rule);
  color:var(--faint); font:400 .72rem/1.7 "IBM Plex Mono",monospace; }}
</style></head><body><div class="wrap">
<h1>GST rate-slab leaderboard</h1>
<p class="sub">Classifying real Indian product descriptions into the GST slabs
actually in force. Ranked by cost per correct answer, which is not the same
ordering as accuracy.</p>
{body}
<ul class="notes">
<li><b>Stale-slab</b> is how often a model quoted a rate that no longer exists —
12% (abolished 22 Sep 2025) or 28% (abolished 1 Feb 2026). It is reported
separately from accuracy because reciting a superseded schedule is a different
failure from being wrong.</li>
<li><b>Failed and unparseable responses count as wrong</b>, not skipped.</li>
<li><b>One prompt for every model.</b> Runs tagged <code>tuned</code> are a
separate per-model pass and are not mixed into this table.</li>
<li>{html.escape(ceiling)}</li>
</ul>
<footer>
Generated {generated} · prices read {PRICES_READ_ON} · FX read {FX_READ_ON} ·
dataset {current_sha[:12] or "none"} ({current_n} rows)<br>
Rates from Notification 9/2025-CT(R) as amended by 19/2025, archived and
hash-pinned in <code>data/reference/primary/</code>.
</footer>
</div></body></html>
"""


def main() -> int:
    runs = latest_per_model(load_all())
    sha, n = dataset_fingerprint()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(runs, sha, n), encoding="utf-8")
    print(f"  wrote {OUT}  ({len(runs)} model(s) ranked)")
    if not runs:
        print("  no runs yet — the page says so rather than showing zeros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
