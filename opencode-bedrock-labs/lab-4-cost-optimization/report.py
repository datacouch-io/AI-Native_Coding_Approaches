#!/usr/bin/env python3
"""Before/after optimisation report across pipeline configurations.

The report deliberately refuses to present a saving as clean when a step failed
its output contract. A pipeline that got cheaper because one stage silently did
nothing has not been optimised - it has been broken, quietly, in a way that a
cost dashboard alone would happily report as a win.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
ORDER = ["baseline", "aggressive", "tuned"]
STEPS = ["implement", "test", "refactor", "document"]


def load(label: str):
    p = RUNS / label / "ledger.json"
    return json.loads(p.read_text()) if p.is_file() else None


def main() -> int:
    ledgers = [(lbl, l) for lbl in ORDER if (l := load(lbl))]
    if not ledgers:
        print("no runs found")
        return 1
    base = dict(ledgers)[ORDER[0]]

    print(f"\n{'PER-STEP COST':<16}" + "".join(f"{lbl:>16}" for lbl, _ in ledgers))
    print("-" * (16 + 16 * len(ledgers)))
    for step in STEPS:
        row = f"{step:<16}"
        for _, l in ledgers:
            s = next((x for x in l["steps"] if x["step"] == step), None)
            if s is None:
                row += f"{'-':>16}"
            else:
                mark = "!" if not s.get("format_ok", True) else " "
                row += f"{s['tier'] + ' $' + format(s['cost_usd'] or 0, '.4f') + mark:>16}"
        print(row)
    print("-" * (16 + 16 * len(ledgers)))
    print(f"{'TOTAL':<16}" + "".join(f"{'$' + format(l['total_cost_usd'], '.4f'):>16}"
                                     for _, l in ledgers))
    print(f"{'WALL CLOCK':<16}" + "".join(f"{format(l['total_elapsed_s'], '.0f') + 's':>16}"
                                          for _, l in ledgers))
    print(f"{'ACCEPTANCE':<16}" + "".join(
        f"{str(l['acceptance']['passed']) + ' pass' if l['acceptance']['green'] else 'RED':>16}"
        for _, l in ledgers))

    print("\nVERSUS BASELINE")
    print(f"  {'config':<14}{'cost':>12}{'saving':>10}{'latency':>11}{'saving':>10}"
          f"   acceptance   verdict")
    print("  " + "-" * 84)
    for lbl, l in ledgers:
        cs = (1 - l["total_cost_usd"] / base["total_cost_usd"]) * 100
        ls = (1 - l["total_elapsed_s"] / base["total_elapsed_s"]) * 100
        acc = f"{l['acceptance']['passed']} pass" if l["acceptance"]["green"] else "RED"
        fails = l.get("format_failures") or []
        if lbl == ORDER[0]:
            verdict = "reference"
        elif fails:
            verdict = f"NOT CLEAN - {','.join(fails)} produced nothing"
        elif l["acceptance"]["green"]:
            verdict = "clean saving"
        else:
            verdict = "REGRESSION"
        print(f"  {lbl:<14}${l['total_cost_usd']:>11.4f}{cs:>9.0f}%"
              f"{l['total_elapsed_s']:>10.0f}s{ls:>9.0f}%   {acc:<12} {verdict}")

    clean = [(lbl, l) for lbl, l in ledgers
             if lbl != ORDER[0] and l["acceptance"]["green"] and not l.get("format_failures")]
    if clean:
        lbl, best = min(clean, key=lambda kv: kv[1]["total_cost_usd"])
        cs = (1 - best["total_cost_usd"] / base["total_cost_usd"]) * 100
        ls = (1 - best["total_elapsed_s"] / base["total_elapsed_s"]) * 100
        print(f"\n  HEADLINE: '{lbl}' delivers the same {best['acceptance']['passed']}"
              f"-test acceptance result for {cs:.0f}% less money and {ls:.0f}% less"
              f" wall-clock time,")
        print(f"            with every pipeline step producing real output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
