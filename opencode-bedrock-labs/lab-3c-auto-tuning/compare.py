#!/usr/bin/env python3
"""Before/after on the same cheap model, split by train and holdout.

The train numbers show the tuner learned something. The HOLDOUT numbers show
whether it learned a rule or just memorised the cases it was shown. Only the
second one is evidence.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = 5


def load(label: str) -> dict:
    return json.loads((HERE / "runs" / f"{label}--all.json").read_text())


def slice_stats(results: list, split: str | None) -> tuple[int, int, int, int]:
    rows = [r for r in results if split is None or r["split"] == split]
    exact = sum(1 for r in rows if r["record_exact"])
    fields = sum(r["fields_correct"] for r in rows)
    return exact, len(rows), fields, len(rows) * FIELDS


def field_breakdown(results: list, split: str | None) -> dict:
    rows = [r for r in results if split is None or r["split"] == split]
    out = {}
    for f in rows[0]["per_field"] if rows else {}:
        out[f] = sum(1 for r in rows if r["per_field"][f])
    return out, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="v1-naive")
    ap.add_argument("--after", default="v2-tuned")
    args = ap.parse_args()

    before, after = load(args.before), load(args.after)
    meta_path = HERE / "runs" / "tune_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    print(f"\nsame model both runs: {before['summary']['model'].split('/')[-1]}")
    print(f"only the prompt changed: {args.before} -> {args.after}\n")

    print(f"{'split':<12}{'records exact':<22}{'fields correct':<22}delta")
    print("-" * 74)
    for split, name in ((None, "ALL"), ("train", "train"), ("holdout", "holdout")):
        be, bn, bf, bft = slice_stats(before["results"], split)
        ae, an, af, aft = slice_stats(after["results"], split)
        d = (af / aft - bf / bft) * 100
        marker = "  <- unseen by the tuner" if split == "holdout" else ""
        print(f"{name:<12}{be}/{bn} -> {ae}/{an:<14}"
              f"{bf}/{bft} ({bf/bft:.0%}) -> {af}/{aft} ({af/aft:.0%})   "
              f"{d:+.0f} pts{marker}")
    print("-" * 74)

    print("\nper-field accuracy on the HOLDOUT split (the honest number)")
    bfields, bn = field_breakdown(before["results"], "holdout")
    afields, an = field_breakdown(after["results"], "holdout")
    for f in bfields:
        print(f"  {f:<20}{bfields[f]}/{bn}  ->  {afields[f]}/{an}")

    cost_before = before["summary"]["total_cost_usd"]
    cost_after = after["summary"]["total_cost_usd"]
    print(f"\neval cost   before ${cost_before}   after ${cost_after}")
    if meta:
        print(f"tuning cost one-off ${meta.get('cost_usd')}  "
              f"({meta.get('elapsed_s')}s, {meta.get('train_failures_shown')} failures shown)")
        print(f"prompt grew {meta.get('base_prompt_chars')} -> "
              f"{meta.get('tuned_prompt_chars')} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
