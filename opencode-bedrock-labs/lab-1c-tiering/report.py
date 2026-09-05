#!/usr/bin/env python3
"""Read the 2x3 matrix along both axes and answer the routing question with numbers.

  ACROSS a vendor row  = vertical tiering  (descend inside one family)
  DOWN   a tier column = horizontal routing (switch vendor, hold the tier)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIERS = ["top", "mid", "low"]
VENDORS = ["Anthropic", "OpenAI"]
TASKS = ["T1", "T2", "T3"]


def load():
    cells = json.loads((HERE / "runs" / "matrix.json").read_text())["cells"]
    return {(c["model"], c["task"]): c for c in cells}, cells


def main() -> int:
    by_key, cells = load()
    models = {}
    for c in cells:
        m = models.setdefault(c["model"], {"vendor": c["vendor"], "tier": c["tier"],
                                           "cost": 0.0, "passed": 0, "total": 0,
                                           "elapsed": 0.0, "no_code": 0})
        m["cost"] += c["cost_usd"]
        m["passed"] += c["passed"]
        m["total"] += c["total"]
        m["elapsed"] += c["elapsed_s"]
        m["no_code"] += 0 if c["format_ok"] else 1

    print(f"\n{'':<12}{'TOP':>26}{'MID':>26}{'LOW':>26}")
    print("-" * 92)
    for vendor in VENDORS:
        row = f"{vendor:<12}"
        for tier in TIERS:
            key = next((k for k, v in models.items()
                        if v["vendor"] == vendor and v["tier"] == tier), None)
            m = models[key]
            pct = (m["passed"] / m["total"] * 100) if m["total"] else 0
            flag = f" !{m['no_code']}nc" if m["no_code"] else ""
            row += f"{key + ' ' + f'{pct:.0f}% ' + '$' + format(m['cost'], '.4f') + flag:>26}"
        print(row)
    print("-" * 92)
    print("  ACROSS a row = vertical tiering   DOWN a column = horizontal routing"
          "   !Nnc = N cells returned no code")

    print("\nVERTICAL - what descending inside one family actually buys you")
    for vendor in VENDORS:
        ordered = [(t, next(k for k, v in models.items()
                            if v["vendor"] == vendor and v["tier"] == t)) for t in TIERS]
        top_cost = models[ordered[0][1]]["cost"]
        print(f"  {vendor}")
        for tier, key in ordered:
            m = models[key]
            pct = (m["passed"] / m["total"] * 100) if m["total"] else 0
            delta = (1 - m["cost"] / top_cost) * 100
            arrow = "reference" if tier == "top" else f"{delta:+.0f}% vs top"
            print(f"    {tier:<5}{key:<9}{pct:>6.0f}%  ${m['cost']:.4f}  "
                  f"{m['elapsed']:>6.1f}s   {arrow}")

    print("\nHORIZONTAL - what switching vendor at a fixed tier buys you")
    for tier in TIERS:
        pair = [(v, next(k for k, m in models.items()
                         if m["vendor"] == v and m["tier"] == tier)) for v in VENDORS]
        (v1, k1), (v2, k2) = pair
        c1, c2 = models[k1]["cost"], models[k2]["cost"]
        cheaper, dearer = (k1, k2) if c1 < c2 else (k2, k1)
        ratio = max(c1, c2) / min(c1, c2)
        p1 = models[k1]["passed"] / models[k1]["total"] * 100 if models[k1]["total"] else 0
        p2 = models[k2]["passed"] / models[k2]["total"] * 100 if models[k2]["total"] else 0
        print(f"  {tier:<5}{k1} {p1:.0f}% ${c1:.4f}   vs   {k2} {p2:.0f}% ${c2:.4f}"
              f"   -> {cheaper} is {ratio:.1f}x cheaper")

    cheapest = min(models.items(), key=lambda kv: kv[1]["cost"])
    perfect = {k: v for k, v in models.items()
               if v["total"] and v["passed"] == v["total"] and not v["no_code"]}
    best = min(perfect.items(), key=lambda kv: kv[1]["cost"]) if perfect else None

    print(f"\n  cheapest overall     : {cheapest[0]} at ${cheapest[1]['cost']:.4f}")
    if best:
        top_costs = [m["cost"] for m in models.values() if m["tier"] == "top"]
        print(f"  cheapest FLAWLESS    : {best[0]} at ${best[1]['cost']:.4f} "
              f"({min(top_costs)/best[1]['cost']:.0f}x cheaper than the cheaper top tier)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
