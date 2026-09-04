#!/usr/bin/env python3
"""Render the model comparison scorecard as a self-contained HTML dashboard.

Input:  artifacts/lab-1/benchmark_results.json (with quality_1_5 merged in)
Output: artifacts/lab-1/dashboard.html
"""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

RESULTS = Path("artifacts/lab-1/benchmark_results.json")
OUT = Path("artifacts/lab-1/dashboard.html")

PALETTE = {
    "claude-sonnet-5": ("#3a2a5c", "#c9aef6"),
    "claude-opus-5":   ("#5c2a3a", "#f6aec2"),
    "gpt-5.6-sol":     ("#2a4a5c", "#ade4f6"),
    "gpt-5.6-terra":   ("#2a5c3a", "#aef6c2"),
}
DEFAULT = ("#2a2f3f", "#c4c9d6")


def stars(q):
    if not q:
        return '<span class="empty">-----</span>'
    q = int(q)
    return "★" * q + f'<span class="empty">{"★" * (5 - q)}</span>'


def badge(model):
    bg, fg = PALETTE.get(model, DEFAULT)
    return f'<span class="badge" style="background:{bg};color:{fg}">{model}</span>'


def bar(value, vmax, color):
    pct = 0 if not vmax else min(100, value / vmax * 100)
    return (f'<div class="track"><div class="fill" style="width:{pct:.1f}%;'
            f'background:{color}"></div></div>')


def main() -> int:
    results = json.loads(RESULTS.read_text())
    ok = [r for r in results if r.get("status", "OK") == "OK" and r.get("cost_usd") is not None]
    if not ok:
        print("ERROR: no successful results to render")
        return 1

    by_model = defaultdict(list)
    for r in ok:
        by_model[r["model"]].append(r)

    summary = {}
    for model, rows in by_model.items():
        qs = [r["quality_1_5"] for r in rows if r.get("quality_1_5")]
        summary[model] = {
            "cost": sum(r["cost_usd"] for r in rows) / len(rows),
            "latency": sum(r["wall_clock_s"] for r in rows) / len(rows),
            "quality": sum(qs) / len(qs) if qs else 0,
            "n": len(rows),
        }

    max_cost = max(s["cost"] for s in summary.values())
    max_lat = max(s["latency"] for s in summary.values())
    total_spend = sum(r["cost_usd"] for r in ok)

    cards = ""
    for model, s in summary.items():
        fg = PALETTE.get(model, DEFAULT)[1]
        cards += f"""
    <div class="card">
      <div class="card-head">{badge(model)}</div>
      <div class="row"><span>Avg cost</span><b>${s['cost']:.4f}</b></div>
      {bar(s['cost'], max_cost, fg)}
      <div class="row"><span>Avg latency</span><b>{s['latency']:.1f}s</b></div>
      {bar(s['latency'], max_lat, fg)}
      <div class="row"><span>Avg quality</span><b>{s['quality']:.2f}/5</b></div>
      <div class="stars">{stars(round(s['quality']))}</div>
    </div>"""

    def table(rows):
        cols = ('<colgroup><col style="width:23%"><col style="width:21%">'
                '<col style="width:13%"><col style="width:13%">'
                '<col style="width:15%"><col style="width:15%"></colgroup>')
        head = ('<tr><th>Model</th><th>Prompt</th><th>Latency</th><th>Cost</th>'
                '<th>Tok in/out</th><th>Quality</th></tr>')
        body = ""
        for r in rows:
            t = r.get("tokens", {})
            body += (
                f'<tr><td>{badge(r["model"])}</td><td>{r["prompt"]}</td>'
                f'<td>{r["wall_clock_s"]:.1f}s</td><td>${r["cost_usd"]:.4f}</td>'
                f'<td>{t.get("input")} / {t.get("output")}</td>'
                f'<td class="stars">{stars(r.get("quality_1_5"))}</td></tr>\n'
            )
        return f"<table>{cols}{head}{body}</table>"

    half = (len(ok) + 1) // 2
    rows_html = f'<div class="cols">{table(ok[:half])}{table(ok[half:])}</div>' 

    # Cheapest model that stays within 75% of the best quality score seen.
    # (An absolute cut-off hides the finding whenever no model scores 4+.)
    top = max(summary, key=lambda m: summary[m]["quality"])
    threshold = 0.75 * summary[top]["quality"]
    good = {m: s for m, s in summary.items() if s["quality"] >= threshold}
    verdict = ""
    if good:
        best = min(good, key=lambda m: good[m]["cost"])
        if best != top:
            mult = summary[top]["cost"] / summary[best]["cost"]
            verdict = (f'<div class="verdict"><b>Verdict:</b> <b>{best}</b> is the cost-effective '
                       f'default &mdash; {summary[best]["quality"]:.2f}/5 average quality at '
                       f'${summary[best]["cost"]:.4f} and {summary[best]["latency"]:.1f}s per task, '
                       f'<b>{mult:.1f}&times; cheaper</b> than {top} '
                       f'({summary[top]["quality"]:.2f}/5, ${summary[top]["cost"]:.4f}, '
                       f'{summary[top]["latency"]:.1f}s). Reserve {top} for the tasks where that '
                       f'quality gap actually pays for itself &mdash; and note this ranking is '
                       f'yours, not a vendor&rsquo;s: it came from your prompts and your ratings.</div>')

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Lab 1 - Model Comparison Scorecard</title>
<style>
 body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;
      color:#e8eaf0;margin:0;padding:32px}}
 h1{{font-size:22px;margin:0 0 4px}}
 .sub{{color:#9aa1b2;font-size:13px;margin-bottom:28px}}
 .section{{font-size:11px;color:#9aa1b2;margin:28px 0 10px;text-transform:uppercase;
          letter-spacing:.06em}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}}
 .card{{background:#171b28;border:1px solid #262b3a;border-radius:8px;padding:16px}}
 .card-head{{margin-bottom:12px}}
 .row{{display:flex;justify-content:space-between;font-size:12px;margin:8px 0 4px;color:#c4c9d6}}
 .row b{{color:#e8eaf0}}
 .track{{background:#1c2130;border-radius:3px;height:8px;overflow:hidden}}
 .fill{{height:100%;border-radius:3px}}
 .badge{{display:inline-block;padding:2px 6px;border-radius:4px;font-weight:600;font-size:11px;
         white-space:nowrap}}
 table{{border-collapse:collapse;width:100%;margin-top:4px;table-layout:fixed}}
 th,td{{text-align:left;padding:6px 7px;border-bottom:1px solid #262b3a;font-size:11px}}
 th{{color:#9aa1b2;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.04em}}
 tr:hover td{{background:#171b28}}
 .stars{{color:#f5c518;letter-spacing:1px}}
 .stars .empty{{color:#3a3f4f}}
 .cols{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;
        align-items:start}}\n .verdict{{margin-top:22px;background:#141a2a;border:1px solid #26324a;border-left:3px solid #4a8fe7;
          border-radius:6px;padding:14px 16px;font-size:13px;line-height:1.6;color:#c4c9d6}}
</style></head><body>
<h1>Lab 1 &mdash; Model Comparison Scorecard</h1>
<div class="sub">{len(set(r['prompt'] for r in ok))} standardized prompts &times;
 {len(summary)} Bedrock model tiers &middot; {len(ok)} live OpenCode runs &middot;
 {date.today().isoformat()} &middot; total real spend ${total_spend:.3f}</div>

<div class="section">Per-model summary (avg of {summary[list(summary)[0]]['n']} prompts)</div>
<div class="grid">{cards}
</div>

<div class="section">Full results — all {len(ok)} runs</div>
{rows_html}
{verdict}
</body></html>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT}")
    print(f"  {len(ok)} results, {len(summary)} models, total spend ${total_spend:.3f}")
    for m, s in sorted(summary.items(), key=lambda kv: kv[1]["cost"]):
        print(f"  {m:<17} avg ${s['cost']:.4f}  {s['latency']:>6.1f}s  {s['quality']:.2f}/5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
