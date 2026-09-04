#!/usr/bin/env python3
"""Compare what each reviewer found, and what it cost to find it.

Maps every confirmed reproducing test onto the three planted defect classes, so
reviewers using different test names can still be compared like for like.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVIEWS = HERE / "reviews"

# The three planted defects, and how to recognise a test that targets each.
DEFECTS = {
    "A: get() does not refresh recency":   re.compile(r"get.*(refresh|recen|lru|evict|order)", re.I),
    "B: capacity off-by-one":              re.compile(r"(capacity|exceed|off_by_one|holds_two)", re.I),
    "C: re-put does not refresh recency":  re.compile(r"(put_existing|reput|re_put|put.*existing)", re.I),
}


def classify_test(name: str) -> str | None:
    # order matters: C is a put-specific case of the recency family, so check it first
    for label in ("C: re-put does not refresh recency",
                  "B: capacity off-by-one",
                  "A: get() does not refresh recency"):
        if DEFECTS[label].search(name):
            return label
    return None


def main() -> int:
    rows = []
    for d in sorted(REVIEWS.iterdir()):
        report = d / "report.json"
        if not report.is_file():
            continue
        r = json.loads(report.read_text())
        v = r["validation"]
        found = {classify_test(t) for t in v["confirmed"]} - {None}
        rows.append({
            "label": d.name,
            "vendor": r["reviewer"]["vendor"],
            "model": r["reviewer"]["model"].split("/")[-1],
            "target": r.get("target", "flawed"),
            "submitted": v["tests_submitted"],
            "confirmed": len(v["confirmed"]),
            "unfair": len(v["unfair_tests"]),
            "no_defect": len(v["no_defect_shown"]),
            "defects_found": found,
            "elapsed_s": r["critique"]["elapsed_s"],
            "cost_usd": r["critique"]["cost_usd"],
        })

    print(f"\n{'reviewer':<16}{'vendor':<11}{'target':<11}{'tests':<7}{'confirmed':<11}"
          f"{'unfair':<8}{'defects':<9}{'time':<9}cost")
    print("-" * 92)
    for r in rows:
        mark = f"{len(r['defects_found'])}/3" if r["target"] == "flawed" else "n/a"
        print(f"{r['label']:<16}{r['vendor']:<11}{r['target']:<11}{r['submitted']:<7}"
              f"{r['confirmed']:<11}{r['unfair']:<8}{mark:<9}"
              f"{r['elapsed_s']:>5.1f}s   ${r['cost_usd']}")
    print("-" * 92)

    print("\nplanted defect coverage (flawed target only)")
    for label in DEFECTS:
        who = [r["label"] for r in rows
               if r["target"] == "flawed" and label in r["defects_found"]]
        print(f"  {label:<38} {', '.join(who) if who else 'MISSED BY ALL'}")

    control = [r for r in rows if r["target"] == "reference"]
    if control:
        print("\ncontrol - reviewing known-good code (any failing test is a false positive)")
        for r in control:
            print(f"  {r['label']:<20} submitted {r['submitted']}, "
                  f"false positives {r['unfair'] + r['confirmed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
