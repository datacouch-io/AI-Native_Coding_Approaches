#!/usr/bin/env python3
"""Run each strategy's generated tests and report correctness + context cost side by side.

The point of the comparison: `isolated` and `contract` used the SAME first hop and the
SAME task. The only thing that changed is whether state was handed between models.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
STRATEGIES = ["isolated", "contract", "full"]
PYTEST = sys.executable

SUMMARY = re.compile(r"(\d+) (passed|failed|error)")


def run_tests(run_dir: Path) -> dict:
    proc = subprocess.run([PYTEST, "-m", "pytest", "test_expenses.py", "-q"],
                          cwd=run_dir, capture_output=True, text=True, timeout=300)
    out = proc.stdout + proc.stderr
    counts = {kind: int(n) for n, kind in SUMMARY.findall(out)}
    collected = "error during collection" not in out and "ImportError" not in out

    first_error = ""
    for line in out.splitlines():
        if line.startswith("E ") and line.strip() != "E":
            # strip absolute paths first - otherwise truncation eats the message
            first_error = line.strip().replace(str(HERE) + "/", "")[:160]
            break

    return {
        "tests_passed": counts.get("passed", 0),
        "tests_failed": counts.get("failed", 0),
        "collected": collected,
        "usable": collected and counts.get("passed", 0) > 0 and counts.get("failed", 0) == 0,
        "first_error": first_error,
        "raw_tail": out.strip().splitlines()[-1] if out.strip() else "",
    }


def main() -> int:
    report = {}
    for strategy in STRATEGIES:
        run_dir = RUNS / strategy
        if not (run_dir / "test_expenses.py").exists():
            print(f"skipping {strategy}: not generated yet", file=sys.stderr)
            continue
        ledger = json.loads((run_dir / "ledger.json").read_text())
        result = run_tests(run_dir)
        # hops 2 and 3 only - hop 1 is shared, so including it would flatter reuse
        handoff_hops = [h for h in ledger["hops"] if h["hop"] != "design"]
        result.update({
            "handoff_input_tokens": sum(h["input_tokens"] or 0 for h in handoff_hops),
            "handoff_cost_usd": round(sum(h["cost_usd"] or 0 for h in handoff_hops), 6),
            "test_prompt_chars": next((h["prompt_chars"] for h in ledger["hops"]
                                       if h["hop"] == "test"), None),
        })
        report[strategy] = result

    print(f"\n{'strategy':<12}{'collects?':<11}{'passed':<9}{'failed':<9}"
          f"{'prompt chars':<14}{'input tok':<11}{'cost':<10}verdict")
    print("-" * 92)
    for strategy, r in report.items():
        verdict = "WORKS" if r["usable"] else "BROKEN"
        print(f"{strategy:<12}{('yes' if r['collected'] else 'NO'):<11}"
              f"{r['tests_passed']:<9}{r['tests_failed']:<9}"
              f"{r['test_prompt_chars']:<14}{r['handoff_input_tokens']:<11}"
              f"${r['handoff_cost_usd']:<9.4f}{verdict}")
    print("-" * 92)
    for strategy, r in report.items():
        if not r["collected"]:
            print(f"{strategy}: {r['first_error']}")

    (HERE.parent / "artifacts" / "lab-2b" / "comparison.json").write_text(
        json.dumps(report, indent=2))
    print("\nwrote artifacts/lab-2b/comparison.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
