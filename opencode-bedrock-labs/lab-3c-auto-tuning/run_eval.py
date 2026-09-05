#!/usr/bin/env python3
"""Run the CHEAP model over the eval set with a given prompt, and score it.

The model, the eval set and the scorer never change between runs. The only
variable is the prompt file - which is the whole point of the experiment.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / ".sandbox"
CHEAP = "amazon-bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"
FIELDS = ["severity", "component", "customer_impact", "affected_version", "reported_at"]

JSON_BLOCK = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def extract_json(text: str):
    """Models wrap JSON in fences, prose, or neither. Try hardest to find an object."""
    for candidate in JSON_BLOCK.findall(text) or []:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def call_cheap(prompt: str, timeout: int) -> tuple[str, float | None, float]:
    start = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", CHEAP, "--format", "json", prompt],
        capture_output=True, text=True, timeout=timeout)
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
    if proc.returncode != 0:
        raise RuntimeError(f"model call failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return text, cost, elapsed


def score(got: dict | None, expected: dict) -> dict:
    """Exact match per field. A missing object scores zero, not a crash."""
    per_field = {}
    for f in FIELDS:
        per_field[f] = (got is not None and f in got and got[f] == expected[f])
    return per_field


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--label", required=True, help="run name, e.g. v1-naive")
    ap.add_argument("--split", default="all", choices=["all", "train", "holdout"])
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    template = Path(args.prompt).read_text()
    cases = json.loads((HERE / "evalset.json").read_text())
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]

    results, total_cost = [], 0.0
    print(f"\nprompt: {args.prompt}   model: {CHEAP.split('/')[-1]}   cases: {len(cases)}\n")

    for case in cases:
        text, cost, elapsed = call_cheap(template.replace("{ticket}", case["input"]),
                                         args.timeout)
        got = extract_json(text)
        per_field = score(got, case["expected"])
        n_ok = sum(per_field.values())
        total_cost += cost or 0
        results.append({
            "id": case["id"], "split": case["split"], "input": case["input"],
            "expected": case["expected"], "got": got, "raw": text[:600],
            "per_field": per_field, "fields_correct": n_ok,
            "record_exact": n_ok == len(FIELDS),
            "cost_usd": cost, "elapsed_s": round(elapsed, 2),
        })
        mark = "OK " if n_ok == len(FIELDS) else "   "
        wrong = [f for f, ok in per_field.items() if not ok]
        print(f"  {mark}{case['id']} [{case['split']:<7}] {n_ok}/{len(FIELDS)}"
              + (f"   missed: {', '.join(wrong)}" if wrong else ""))

    fields_total = len(cases) * len(FIELDS)
    fields_ok = sum(r["fields_correct"] for r in results)
    exact = sum(1 for r in results if r["record_exact"])
    summary = {
        "label": args.label, "prompt_file": args.prompt, "model": CHEAP,
        "split": args.split, "cases": len(cases),
        "records_exact": exact, "records_total": len(cases),
        "fields_correct": fields_ok, "fields_total": fields_total,
        "field_accuracy": round(fields_ok / fields_total, 4),
        "record_accuracy": round(exact / len(cases), 4),
        "total_cost_usd": round(total_cost, 6),
    }
    out = HERE / "runs" / f"{args.label}--{args.split}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    print(f"\n  records exact : {exact}/{len(cases)}   ({summary['record_accuracy']:.0%})")
    print(f"  fields correct: {fields_ok}/{fields_total}   ({summary['field_accuracy']:.0%})")
    print(f"  cost: ${summary['total_cost_usd']}   ->  {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
