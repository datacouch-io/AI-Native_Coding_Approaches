#!/usr/bin/env python3
"""Auto-tuning: a high-tier model reads the cheap model's failures and rewrites its prompt.

Two rules make this an experiment rather than a demo:

  1. The tuner sees ONLY the train split. The holdout cases are never shown to it.
  2. The tuner is told not to enumerate the cases it was shown - it must infer the
     general rule, because the tuned prompt is scored on inputs it never saw.

Without those, "tuning" degenerates into pasting the answer key into the prompt,
and the improvement means nothing.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sandbox"
TUNER = "amazon-bedrock/us.anthropic.claude-opus-5"
BLOCK = re.compile(r"```(?:text|txt|prompt)?\s*\n(.*?)```", re.DOTALL)

TUNE_TEMPLATE = """You are optimising a prompt that will be run by a much cheaper, weaker model
(Claude Haiku). The task is structured extraction from free-text support tickets.

## The prompt as it stands

```
{prompt}
```

## How it scored

{score_line}

## The cases it got wrong

Each entry shows the input, what the cheap model produced, and what was required.

{failures}

---

Work out the *general rules* these failures violate - the normalisation policy, the
enum vocabularies, how absent values must be represented, and the output discipline
the cheap model is not following. Then rewrite the prompt so a weak model follows
those rules reliably.

Hard requirements:

- Keep the literal placeholder `{{ticket}}` exactly once, where the ticket text goes.
- Do NOT enumerate or restate the specific cases above. This prompt is scored on
  inputs you have not seen, so a lookup table of these examples is worthless. State
  rules, not answers.
- Be explicit about every enum's allowed values, and about how to represent a value
  that is genuinely absent.
- Keep it tight. A weak model follows a short, unambiguous instruction better than a
  long essay.

Return the complete new prompt as a single fenced code block, and nothing else."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-run", default="runs/v1-naive--all.json")
    ap.add_argument("--base-prompt", default="prompts/v1-naive.txt")
    ap.add_argument("--out", default="prompts/v2-tuned.txt")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    run = json.loads((HERE / args.from_run).read_text())
    # TRAIN ONLY. The holdout split is the honesty check and must stay unseen.
    train = [r for r in run["results"] if r["split"] == "train"]
    failures = [r for r in train if not r["record_exact"]]
    if not failures:
        print("no train failures to learn from")
        return 1

    blocks = []
    for r in failures:
        wrong = {f: {"got": (r["got"] or {}).get(f, "<missing>"), "expected": r["expected"][f]}
                 for f, ok in r["per_field"].items() if not ok}
        blocks.append(f"### {r['id']}\ninput: {r['input']}\nwrong fields: "
                      f"{json.dumps(wrong, indent=2)}")

    tr_fields = sum(r["fields_correct"] for r in train)
    score_line = (f"On the {len(train)} cases shown below's split: "
                  f"{sum(1 for r in train if r['record_exact'])}/{len(train)} records fully "
                  f"correct, {tr_fields}/{len(train) * 5} individual fields correct.")

    prompt = TUNE_TEMPLATE.format(
        prompt=(HERE / args.base_prompt).read_text(),
        score_line=score_line,
        failures="\n\n".join(blocks))

    print(f"tuning with {TUNER.split('/')[-1]} on {len(failures)} train failures "
          f"({len(train)} train cases; holdout withheld) ...")
    start = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", TUNER, "--format", "json", prompt],
        capture_output=True, text=True, timeout=args.timeout)
    elapsed = time.time() - start

    text, cost = "", None
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "text":
            text += ev["part"].get("text", "")
        if ev.get("type") == "step_finish":
            cost = ev["part"].get("cost")
    if proc.returncode != 0 or not text.strip():
        print(f"tuner failed (exit {proc.returncode}): {proc.stderr[:300]}")
        return 1

    found = BLOCK.findall(text)
    if not found:
        print("tuner returned no fenced prompt block")
        (HERE / "runs" / "tuner-raw.md").write_text(text)
        return 1
    tuned = max(found, key=len).strip() + "\n"
    if "{ticket}" not in tuned:
        print("ERROR: tuned prompt lost the {ticket} placeholder - refusing to write it")
        (HERE / "runs" / "tuner-raw.md").write_text(text)
        return 1

    (HERE / args.out).write_text(tuned)
    (HERE / "runs" / "tune_meta.json").write_text(json.dumps({
        "tuner": TUNER, "elapsed_s": round(elapsed, 2), "cost_usd": cost,
        "train_failures_shown": len(failures),
        "base_prompt_chars": len((HERE / args.base_prompt).read_text()),
        "tuned_prompt_chars": len(tuned),
    }, indent=2))
    print(f"  wrote {args.out}  ({len(tuned)} chars, was "
          f"{len((HERE / args.base_prompt).read_text())})  {elapsed:.1f}s  ${cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
