#!/usr/bin/env python3
"""Execute Mode: build the module one milestone at a time, with a test gate between steps.

For each milestone the fast model gets: the task, the plan, the current file, and
- on a retry - the real pytest failure output. After it writes, the acceptance
tests for THIS milestone and every earlier one are run. A step is only accepted
when that whole cumulative gate is green, so step 4 cannot silently break step 1.

The models never see tests/test_acceptance.py: every hop runs in an empty sandbox.
The gate has to grade the work, not be copied from.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sandbox"
SONNET = "amazon-bedrock/us.anthropic.claude-sonnet-5"
TARGET = HERE / "exporter.py"
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)

MILESTONES = [
    ("M1", "to_csv",      "TestM1ToCsv"),
    ("M2", "to_json",     "TestM2ToJson"),
    ("M3", "filter_rows", "TestM3FilterRows"),
    ("M4", "export",      "TestM4Export"),
]

STEP_TEMPLATE = """{task}

---

## The agreed build plan

{plan}

---

## Your assignment: milestone {mid} ({name}) - and only this milestone

{current}

Implement milestone {mid} exactly as the plan specifies. Keep every earlier
milestone working - the acceptance suite re-runs all of them.
{failure}
You cannot create files. Return the COMPLETE contents of `exporter.py` as a single
fenced ```python block, and nothing else."""

RETRY_BLOCK = """
Your previous attempt FAILED the acceptance gate. This is the real pytest output:

```
{output}
```

Fix the cause. Do not change behaviour the gate did not complain about.
"""


def run_model(prompt: str, timeout: int) -> tuple[str, float | None, float]:
    start = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", SONNET, "--format", "json", prompt],
        capture_output=True, text=True, timeout=timeout)
    elapsed = time.time() - start
    text, cost = "", None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text += event["part"].get("text", "")
        if event.get("type") == "step_finish":
            cost = event["part"].get("cost")
    if proc.returncode != 0 or not text.strip():
        raise RuntimeError(f"model call failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return text, cost, elapsed


def run_gate(upto: int) -> tuple[bool, int, int, str, list[str]]:
    """Run acceptance classes for milestones 1..upto.

    Returns (ok, passed, failed, output, failing_test_names).
    """
    classes = " or ".join(cls for _, _, cls in MILESTONES[:upto])
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_acceptance.py", "-k", classes, "-q"],
        cwd=HERE, capture_output=True, text=True, timeout=300)
    out = proc.stdout + proc.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    names = re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.MULTILINE)
    return proc.returncode == 0, passed, failed + errors, out, names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="PLAN.md")
    ap.add_argument("--max-retries", type=int, default=1,
                    help="extra attempts per milestone after a failed gate")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--ledger", default="../artifacts/lab-3/execution_ledger.json")
    args = ap.parse_args()

    plan = (HERE / args.plan).read_text()
    task = (HERE / "TASK.md").read_text()
    TARGET.unlink(missing_ok=True)

    ledger = {"model": SONNET, "milestones": []}
    print(f"\nexecuting {len(MILESTONES)} milestones with {SONNET.split('/')[-1]}\n")

    for index, (mid, name, _cls) in enumerate(MILESTONES, start=1):
        record = {"milestone": mid, "function": name, "attempts": []}
        failure_text = ""
        accepted = False

        for attempt in range(1, args.max_retries + 2):
            current = (f"The current contents of `exporter.py`:\n\n```python\n"
                       f"{TARGET.read_text()}\n```\n" if TARGET.exists()
                       else "`exporter.py` does not exist yet. Create it.")
            prompt = STEP_TEMPLATE.format(
                task=task, plan=plan, mid=mid, name=name,
                current=current,
                failure=RETRY_BLOCK.format(output=failure_text) if failure_text else "")

            text, cost, elapsed = run_model(prompt, args.timeout)
            blocks = CODE_BLOCK.findall(text)
            if not blocks:
                raise RuntimeError(f"{mid} attempt {attempt}: no code block returned")
            TARGET.write_text(max(blocks, key=len))

            ok, passed, failed, output, failing = run_gate(index)
            record["attempts"].append({
                "attempt": attempt, "cost_usd": cost, "elapsed_s": round(elapsed, 2),
                "gate_passed": ok, "tests_passed": passed, "tests_failed": failed,
                "failing_tests": failing,
            })
            status = "PASS" if ok else "FAIL"
            print(f"  {mid} {name:<12} attempt {attempt}  {status}  "
                  f"{passed} passed / {failed} failed  {elapsed:5.1f}s  ${cost}")

            if ok:
                accepted = True
                break
            # feed the real failure back into the next attempt
            failure_text = "\n".join(output.strip().splitlines()[-25:])
            for name in failing[:3]:
                print(f"       caught: {name}")
            print(f"     gate failed - retrying with the pytest output")

        record["accepted"] = accepted
        record["total_cost_usd"] = round(sum(a["cost_usd"] or 0 for a in record["attempts"]), 6)
        ledger["milestones"].append(record)
        if not accepted:
            print(f"\n  {mid} still failing after {len(record['attempts'])} attempts - stopping.")
            break

    ok_all, passed, failed, _, _ = run_gate(len(MILESTONES))
    ledger["final_gate"] = {"passed": passed, "failed": failed, "green": ok_all}
    ledger["total_cost_usd"] = round(
        sum(m["total_cost_usd"] for m in ledger["milestones"]), 6)
    ledger["milestones_accepted"] = sum(1 for m in ledger["milestones"] if m["accepted"])

    out = Path(args.ledger)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2))

    print(f"\n  final gate: {passed} passed, {failed} failed"
          f"   milestones accepted: {ledger['milestones_accepted']}/{len(MILESTONES)}")
    print(f"  execute cost: ${ledger['total_cost_usd']}   ledger: {out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
