#!/usr/bin/env python3
"""Attach a 1-5 quality rating to each benchmark result and emit the scorecard.

Two modes:
  python3 tools/score.py --interactive   # review each response, type a 1-5 score
  python3 tools/score.py                 # merge scores -> scorecard.csv

Scores live in artifacts/lab-1/quality_scores.csv so a rating pass is re-runnable
and reviewable, instead of being typed straight into a JSON file by hand.
"""
import argparse
import csv
import json
from pathlib import Path

RESULTS = Path("artifacts/lab-1/benchmark_results.json")
RESPONSES = Path("artifacts/lab-1/responses")
SCORES = Path("artifacts/lab-1/quality_scores.csv")
SCORECARD = Path("artifacts/lab-1/scorecard.csv")

RUBRIC = """
  5 = correct, complete, production-shaped (handles edges, documented, no bugs)
  4 = correct and usable, minor gaps (thin edge cases or docs)
  3 = broadly correct, needs real edits before use
  2 = partially correct / misses a stated requirement
  1 = wrong, or ignored the prompt
"""


def load_scores() -> dict:
    if not SCORES.exists():
        return {}
    with SCORES.open() as f:
        return {(r["model"], r["prompt"]): int(r["quality_1_5"]) for r in csv.DictReader(f)}


def save_scores(scores: dict) -> None:
    SCORES.parent.mkdir(parents=True, exist_ok=True)
    with SCORES.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "prompt", "quality_1_5"])
        for (model, prompt), q in sorted(scores.items()):
            w.writerow([model, prompt, q])


def interactive(results: list) -> None:
    scores = load_scores()
    print("Rate each response 1-5. Enter = keep existing, s = skip, q = save and quit.")
    print(RUBRIC)
    for row in results:
        key = (row["model"], row["prompt"])
        current = scores.get(key)
        path = RESPONSES / f"{row['model']}__{row['prompt']}.md"
        text = path.read_text() if path.exists() else "(no captured response)"

        print("\n" + "=" * 72)
        print(f"MODEL: {row['model']}   PROMPT: {row['prompt']}")
        print(f"cost=${row.get('cost_usd')}  latency={row.get('wall_clock_s')}s  chars={len(text)}")
        print("-" * 72)
        print(text[:1200] + ("\n...[truncated]" if len(text) > 1200 else ""))
        print("-" * 72)

        while True:
            raw = input(f"quality 1-5 [{current if current else '-'}]: ").strip().lower()
            if raw == "q":
                save_scores(scores)
                print(f"Saved {len(scores)} scores to {SCORES}")
                return
            if raw in ("s", ""):
                break
            if raw in {"1", "2", "3", "4", "5"}:
                scores[key] = int(raw)
                break
            print("  enter 1-5, or s/q")
    save_scores(scores)
    print(f"\nSaved {len(scores)} scores to {SCORES}")


def merge(results: list) -> int:
    scores = load_scores()
    missing = []
    for row in results:
        key = (row["model"], row["prompt"])
        if key in scores:
            row["quality_1_5"] = scores[key]
        else:
            missing.append(key)

    RESULTS.write_text(json.dumps(results, indent=2))

    with SCORECARD.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "prompt", "wall_clock_s", "cost_usd",
                    "quality_1_5", "input_tokens", "output_tokens"])
        for r in results:
            t = r.get("tokens", {})
            w.writerow([r["model"], r["prompt"], r["wall_clock_s"], r.get("cost_usd"),
                        r.get("quality_1_5", ""), t.get("input"), t.get("output")])

    print(f"Wrote {SCORECARD} ({len(results)} rows)")
    if missing:
        print(f"WARNING: {len(missing)} unrated - run with --interactive:")
        for m in missing:
            print(f"  - {m[0]} / {m[1]}")
        return 1
    print("All results rated.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interactive", action="store_true", help="review and rate each response")
    args = ap.parse_args()

    results = json.loads(RESULTS.read_text())
    if args.interactive:
        interactive(results)
        results = json.loads(RESULTS.read_text())
    return merge(results)


if __name__ == "__main__":
    raise SystemExit(main())
