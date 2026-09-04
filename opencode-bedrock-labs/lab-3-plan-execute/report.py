#!/usr/bin/env python3
"""Render the execution ledger as the plan-and-execute summary.

Reads the recorded run rather than re-running it, so the summary always matches
the artifacts on disk.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE.parent / "artifacts" / "lab-3" / "execution_ledger.json"
PLAN_META = HERE / "plan_meta.json"


def main() -> int:
    ledger = json.loads(LEDGER.read_text())
    plan = json.loads(PLAN_META.read_text()) if PLAN_META.exists() else {}

    print("\nPLAN MODE")
    if plan:
        print(f"  {plan['model'].split('/')[-1]:<28} {plan['elapsed_s']:>6.1f}s  "
              f"${plan['cost_usd']}   {plan['plan_chars']} chars of plan")

    print(f"\nEXECUTE MODE  ({ledger['model'].split('/')[-1]})")
    print(f"  {'milestone':<22}{'attempt':<9}{'gate':<7}{'cumulative tests':<19}"
          f"{'time':<9}cost")
    print("  " + "-" * 74)
    for m in ledger["milestones"]:
        for a in m["attempts"]:
            gate = "PASS" if a["gate_passed"] else "FAIL"
            tests = f"{a['tests_passed']} passed / {a['tests_failed']} failed"
            print(f"  {m['milestone'] + ' ' + m['function']:<22}{a['attempt']:<9}{gate:<7}"
                  f"{tests:<19}{a['elapsed_s']:>5.1f}s   ${a['cost_usd']}")
            for name in a.get("failing_tests", [])[:3]:
                print(f"  {'':<22}{'':<9}caught: {name.split('::')[-1]}")
    print("  " + "-" * 74)

    fg = ledger["final_gate"]
    total = ledger["total_cost_usd"] + (plan.get("cost_usd") or 0)
    print(f"  final gate: {fg['passed']} passed, {fg['failed']} failed   "
          f"milestones accepted: {ledger['milestones_accepted']}/{len(ledger['milestones'])}")
    print(f"  plan ${plan.get('cost_usd', 0):.4f} + execute ${ledger['total_cost_usd']:.4f}"
          f" = ${total:.4f} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
