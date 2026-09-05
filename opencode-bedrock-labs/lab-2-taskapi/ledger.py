#!/usr/bin/env python3
"""Extract the real cost of each orchestration hop from OpenCode's captured runs.

Lab 2's claim is that routing design to a high tier and implementation to a low
tier is worth doing. That is an economic claim, so it needs numbers. This reads
the `--format json` event streams already captured in artifacts/lab-2/ and totals
them per hop.

Note on correctness: a single `opencode run` can emit SEVERAL `step_finish`
events - one per model step, including any tool-use round trips. The cost of a
run is the SUM of them. Reading only the last one undercounts, sometimes badly.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent / "artifacts" / "lab-2"

# Filename -> (feature, phase, tier). OpenCode's event stream does not record the
# model id, so the mapping is declared here rather than guessed.
RUNS = [
    ("plan-opus5.jsonl",                "search endpoint", "design (plan mode)",  "opus"),
    ("build-sonnet5.jsonl",             "search endpoint", "build (implement)",   "sonnet"),
    ("plan2-opus5-bulkdelete.jsonl",    "bulk delete",     "design (plan mode)",  "opus"),
    ("build2-sonnet5-bulkdelete.jsonl", "bulk delete",     "build (implement)",   "sonnet"),
]
VARIANTS = [
    ("plan-opus5.jsonl",              "full prompt, repo readable"),
    ("plan-opus5-NAIVE-PROMPT.jsonl", "one-line prompt"),
    ("plan-opus5-NO-REPO.jsonl",      "full prompt, repo NOT readable"),
]


def totals(path: Path) -> dict:
    cost, out_tokens, steps = 0.0, 0, 0
    for line in path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "step_finish":
            part = ev["part"]
            cost += part.get("cost") or 0
            out_tokens += (part.get("tokens") or {}).get("output") or 0
            steps += 1
    return {"cost_usd": round(cost, 6), "output_tokens": out_tokens, "steps": steps}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    ledger = {"features": {}, "variants": []}
    print(f"\n{'FEATURE':<18}{'PHASE':<22}{'TIER':<9}{'STEPS':>6}{'OUT TOK':>9}{'COST':>11}")
    print("-" * 75)

    for fname, feature, phase, tier in RUNS:
        p = ARTIFACTS / fname
        if not p.is_file():
            print(f"  missing: {fname}")
            continue
        t = totals(p)
        ledger["features"].setdefault(feature, {})[phase] = {**t, "tier": tier, "run": fname}
        print(f"{feature:<18}{phase:<22}{tier:<9}{t['steps']:>6}{t['output_tokens']:>9}"
              f"{'$' + format(t['cost_usd'], '.4f'):>11}")
    print("-" * 75)

    print(f"\n{'FEATURE':<18}{'DESIGN':>12}{'BUILD':>12}{'TOTAL':>12}   DESIGN SHARE")
    print("-" * 75)
    for feature, phases in ledger["features"].items():
        d = phases.get("design (plan mode)", {}).get("cost_usd", 0)
        b = phases.get("build (implement)", {}).get("cost_usd", 0)
        total = d + b
        share = (d / total * 100) if total else 0
        ratio = (d / b) if b else float("inf")
        ledger["features"][feature]["_summary"] = {
            "design_usd": d, "build_usd": b, "total_usd": round(total, 6),
            "design_share_pct": round(share, 1), "design_to_build_ratio": round(ratio, 1),
        }
        print(f"{feature:<18}{'$' + format(d, '.4f'):>12}{'$' + format(b, '.4f'):>12}"
              f"{'$' + format(total, '.4f'):>12}   {share:.0f}%  ({ratio:.0f}x the build)")
    print("-" * 75)

    print(f"\nDESIGN-HOP VARIANTS - same model, same feature, different prompt")
    print(f"  {'variant':<34}{'out tok':>9}{'cost':>11}")
    print("  " + "-" * 54)
    for fname, label in VARIANTS:
        p = ARTIFACTS / fname
        if not p.is_file():
            continue
        t = totals(p)
        ledger["variants"].append({"run": fname, "label": label, **t})
        print(f"  {label:<34}{t['output_tokens']:>9}{'$' + format(t['cost_usd'], '.4f'):>11}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(ledger, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
