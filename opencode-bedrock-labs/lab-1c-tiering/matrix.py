#!/usr/bin/env python3
"""Run the same task battery down two vendor ladders, so both tiering axes are
measured against identical work.

              TOP TIER        MID TIER        LOW TIER
  Anthropic   opus            sonnet          haiku
  OpenAI      sol             luna            terra

Reading DOWN a column is horizontal routing - switching vendor at a fixed tier.
Reading ACROSS a row is vertical tiering - descending inside one family.
Because the tasks and the graders are identical, the two axes are comparable,
which is the whole point.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sandbox"
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)

GRID = [
    # (vendor, tier, key, model id)
    ("Anthropic", "top", "opus",   "amazon-bedrock/us.anthropic.claude-opus-5"),
    ("Anthropic", "mid", "sonnet", "amazon-bedrock/us.anthropic.claude-sonnet-5"),
    ("Anthropic", "low", "haiku",
     "amazon-bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("OpenAI",    "top", "sol",    "amazon-bedrock/global.openai.gpt-5.6-sol"),
    ("OpenAI",    "mid", "luna",   "amazon-bedrock/global.openai.gpt-5.6-luna"),
    ("OpenAI",    "low", "terra",  "amazon-bedrock/global.openai.gpt-5.6-terra"),
]
TASKS = ["T1", "T2", "T3"]

# NOTE on the wording. An earlier version of this prompt said "implement the
# function in a module named solution.py". Under `--agent plan` - which is
# read-only - that reads as an instruction to CREATE A FILE, and the models
# correctly refused: haiku replied "this creates a conflict with being in plan
# mode. How would you like me to proceed?" and sonnet returned a numbered plan
# inside a python fence. That was a harness bug, not a capability difference,
# and scoring it as one would have libelled the cheaper tiers.
#
# The fix is the phrasing Labs 1, 3 and 4 already use: ask for the file's
# CONTENTS as response text, and say plainly that no file can be created.
PROMPT = """{spec}

---

You cannot create or edit files. Return the COMPLETE CONTENTS of `solution.py`
as response text.

OUTPUT CONTRACT - you are running inside an automated harness with no human to
answer you:
- Do NOT ask questions or propose options. Do NOT explain your approach.
- Do NOT produce a plan. Produce the finished code.
- Your entire reply must be ONE fenced ```python code block and nothing outside it.
- The block must contain the complete module, imports included.
"""


def task_spec(task: str) -> str:
    """Pull just this task's section out of SPEC.md - a model sees one task at a time."""
    text = (HERE / "SPEC.md").read_text()
    blocks = re.split(r"\n---\n", text)
    for b in blocks:
        if re.search(rf"^##\s+{task}\b", b.strip(), re.MULTILINE):
            return b.strip()
    raise KeyError(f"no spec section for {task}")


def run_model(model_id: str, prompt: str, timeout: int):
    start = time.time()
    try:
        proc = subprocess.run(
            ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
             "--model", model_id, "--format", "json", prompt],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # An 18-cell batch must survive one hung call. Record it and move on.
        return "", 0.0, round(time.time() - start, 2), "TIMEOUT", {}
    elapsed = time.time() - start
    text, cost = "", 0.0
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "text":
            text += ev["part"].get("text", "")
        if ev.get("type") == "step_finish":
            part = ev["part"]
            cost += part.get("cost") or 0            # SUM - see Lab 2, step 8
            t = part.get("tokens") or {}
            tok["input"] += t.get("input") or 0
            tok["output"] += t.get("output") or 0
            tok["reasoning"] += t.get("reasoning") or 0
            cache = t.get("cache") or {}
            tok["cache_read"] += cache.get("read") or 0
            tok["cache_write"] += cache.get("write") or 0
    return text, round(cost, 6), round(elapsed, 2), proc.returncode, tok


def grade(code: str, task: str) -> tuple[int, int, bool]:
    """Run the hidden suite for this task. Returns (passed, total, imported)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "solution.py").write_text(code)
        shutil.copy(HERE / "tests" / f"test_{task.lower()}.py", work / "test_suite.py")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_suite.py", "-q", "--tb=no",
             "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True, timeout=300)
        out = proc.stdout + proc.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    imported = "ImportError" not in out and "error during collection" not in out
    return passed, passed + failed + errors, imported


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--only", default=None, help="comma-separated model keys")
    args = ap.parse_args()

    grid = [g for g in GRID if not args.only or g[2] in args.only.split(",")]
    out_dir = HERE / "runs"
    out_dir.mkdir(exist_ok=True)
    ledger_path = out_dir / "matrix.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.is_file() else {"cells": []}
    done = {(c["model"], c["task"]) for c in ledger["cells"] if c.get("format_ok")}
    if done:
        print(f"resuming - {len(done)} cells already recorded")

    print(f"\n{'model':<9}{'vendor':<11}{'tier':<6}{'task':<6}{'score':<10}"
          f"{'time':>8}{'cost':>11}")
    print("-" * 62)

    for vendor, tier, key, model_id in grid:
        for task in TASKS:
            if (key, task) in done:
                continue
            text, cost, elapsed, rc, tok = run_model(
                model_id, PROMPT.format(spec=task_spec(task)), args.timeout)
            blocks = CODE_BLOCK.findall(text)
            if rc == "TIMEOUT":
                cell = {"vendor": vendor, "tier": tier, "model": key, "task": task,
                        "passed": 0, "total": 0, "format_ok": False, "timed_out": True,
                        "cost_usd": 0.0, "elapsed_s": elapsed, "tokens": {}}
                print(f"{key:<9}{vendor:<11}{tier:<6}{task:<6}{'TIMEOUT':<10}"
                      f"{elapsed:>7.1f}s{'-':>11}")
            elif rc != 0 or not blocks:
                cell = {"vendor": vendor, "tier": tier, "model": key, "task": task,
                        "passed": 0, "total": 0, "format_ok": False,
                        "cost_usd": cost, "elapsed_s": elapsed, "tokens": tok,
                        "raw_reply_chars": len(text)}
                (out_dir / f"{key}--{task}.reply.md").write_text(text)
                print(f"{key:<9}{vendor:<11}{tier:<6}{task:<6}{'NO CODE':<10}"
                      f"{elapsed:>7.1f}s{'$' + format(cost, '.4f'):>11}")
            else:
                code = max(blocks, key=len)
                (out_dir / f"{key}--{task}.py").write_text(code)
                passed, total, imported = grade(code, task)
                cell = {"vendor": vendor, "tier": tier, "model": key, "task": task,
                        "passed": passed, "total": total, "format_ok": True,
                        "imported": imported, "cost_usd": cost, "elapsed_s": elapsed,
                        "tokens": tok}
                pct = (passed / total * 100) if total else 0
                print(f"{key:<9}{vendor:<11}{tier:<6}{task:<6}"
                      f"{f'{passed}/{total} ({pct:.0f}%)':<10}"
                      f"{elapsed:>7.1f}s{'$' + format(cost, '.4f'):>11}")
            ledger["cells"] = [c for c in ledger["cells"]
                               if not (c["model"] == key and c["task"] == task)]
            ledger["cells"].append(cell)
            ledger_path.write_text(json.dumps(ledger, indent=2))

    print("-" * 62)
    print(f"  {len(ledger['cells'])} cells   "
          f"total ${sum(c['cost_usd'] for c in ledger['cells']):.4f}   "
          f"-> runs/matrix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
