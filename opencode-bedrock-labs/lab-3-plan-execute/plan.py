#!/usr/bin/env python3
"""Plan Mode: have the high-reasoning model turn TASK.md into an ordered build plan.

The output is a plan document a *different, cheaper* model will execute one
milestone at a time. That is the whole point of the split: reasoning is bought
once, at the top, and the expensive model never touches the repetitive work.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sandbox"
OPUS = "amazon-bedrock/us.anthropic.claude-opus-5"

# The structured Plan Mode template. Everything the planner needs is IN the prompt -
# it runs in an empty sandbox and cannot read the repo (see the lab's Step 2).
PLAN_TEMPLATE = """{task}

---

You are the PLANNER. Do not write the implementation.

Produce an ordered build plan that another engineer - working with a faster, less
capable model, one milestone at a time - can follow without ever seeing this
conversation. For each of the four milestones M1..M4, give:

1. **Goal** - one sentence on what exists when the milestone is done.
2. **Design decisions** - the choices the implementer would otherwise get wrong:
   data structures, helper functions, how a missing nested path is represented
   internally, and how that sentinel differs from a real `None` value.
3. **Implementation notes** - the specific functions to add or change, and any
   shared helper the later milestones will depend on.
4. **Self-check** - what the implementer should manually confirm before moving on.

Rules for the plan:
- Milestones build on each other. State explicitly what M2, M3 and M4 each reuse
  from earlier milestones, so the implementer does not reinvent or break it.
- Call out the traps in this spec that a fast model will otherwise miss.
- The implementer will be given ONLY this plan, the task, and the current file.
  Anything you leave implicit will be guessed.

Return markdown only."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="PLAN.md")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    prompt = PLAN_TEMPLATE.format(task=(HERE / "TASK.md").read_text())
    print(f"planning with {OPUS.split('/')[-1]} ...", flush=True)

    start = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", OPUS, "--format", "json", prompt],
        capture_output=True, text=True, timeout=args.timeout)
    elapsed = time.time() - start

    text, cost, tokens = "", None, {}
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text += event["part"].get("text", "")
        if event.get("type") == "step_finish":
            cost = event["part"].get("cost")
            tokens = event["part"].get("tokens", {})
    if proc.returncode != 0 or not text.strip():
        print(f"planner failed (exit {proc.returncode}): {proc.stderr[:400]}", file=sys.stderr)
        return 1

    (HERE / args.out).write_text(text)
    meta = {"model": OPUS, "elapsed_s": round(elapsed, 2), "cost_usd": cost,
            "output_tokens": tokens.get("output"), "plan_chars": len(text)}
    (HERE / "plan_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  wrote {args.out}  {len(text)} chars  {elapsed:.1f}s  ${cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
