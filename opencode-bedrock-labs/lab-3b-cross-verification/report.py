#!/usr/bin/env python3
"""Render one verification run from its recorded report, so the summary always
matches the artifacts on disk rather than a fresh (and differently-priced) run."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="terra")
    args = ap.parse_args()
    r = json.loads((HERE / "reviews" / args.label / "report.json").read_text())

    rv, v = r["reviewer"], r["validation"]
    print(f"\nVERIFICATION RUN  target={r.get('target', 'flawed')}")
    print(f"  reviewer   {rv['vendor']:<10} {rv['model'].split('/')[-1]}")
    print(f"             {r['critique']['elapsed_s']}s   ${r['critique']['cost_usd']}"
          f"   review {r['critique']['review_chars']} chars")

    print(f"\n  VALIDATION   {v['tests_submitted']} reproducing tests submitted")
    for name in v["confirmed"]:
        print(f"    CONFIRMED  {name}")
    for name in v["unfair_tests"]:
        print(f"    UNFAIR     {name}   (fails on correct code too)")
    for name in v["no_defect_shown"]:
        print(f"    NO DEFECT  {name}   (passes on the flawed code)")

    if "revision" in r:
        rev = r["revision"]
        print(f"\n  REVISION     {rev['vendor']} {rev['model'].split('/')[-1]}"
              f"   {rev['elapsed_s']}s   ${rev['cost_usd']}")
        rq = r["reverify"]
        print(f"\n  RE-VERIFY    reviewer tests still failing: "
              f"{len(rq['reviewer_tests_still_failing'])}")
        print(f"               hidden ground truth: {len(rq['hidden_failing_before'])} failing "
              f"before -> {len(rq['hidden_failing_after'])} failing after "
              f"(of {rq['hidden_total']})")
        for name in rq["hidden_failing_before"]:
            print(f"                 fixed: {name}")
        print(f"\n  TOTAL COST   ${r['total_cost_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
