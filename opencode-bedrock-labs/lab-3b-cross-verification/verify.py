#!/usr/bin/env python3
"""Cross-model verification: generate -> critique -> revise -> re-verify.

The hard part of a review loop is not getting a critique. It is deciding whether
a critique is TRUE. So the reviewer must submit, with every defect it claims, a
pytest test that reproduces it. The harness then runs those tests twice:

    against the flawed module     - a real defect makes the test FAIL
    against a correct reference   - a fair test PASSES

A finding is CONFIRMED only if it fails the first and passes the second. A test
that fails both is a bad test, not a discovery - and this is what separates a
verification system from a model that sounds confident.
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
FLAWED = HERE / "lru_cache.py"
REFERENCE = HERE / ".reference" / "lru_cache.py"
HIDDEN = HERE / "tests" / "test_hidden.py"

MODELS = {
    "sonnet": ("Anthropic", "amazon-bedrock/us.anthropic.claude-sonnet-5"),
    "opus":   ("Anthropic", "amazon-bedrock/us.anthropic.claude-opus-5"),
    "terra":  ("OpenAI",    "amazon-bedrock/global.openai.gpt-5.6-terra"),
    "sol":    ("OpenAI",    "amazon-bedrock/global.openai.gpt-5.6-sol"),
}

CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)

REVIEW_TEMPLATE = """You are the VERIFIER. Another engineer wrote the module below against this
specification. Your job is to find where the code does NOT satisfy the spec.

## Specification

{spec}

## The code under review

```python
{code}
```

---

Review the code against every numbered rule in the contract. For each defect you
find, you must provide a pytest test that REPRODUCES it - a test that fails on the
code above and would pass on a correct implementation.

Return exactly two things:

1. A markdown section `## Findings` - a numbered list. One line per defect: which
   contract rule it breaks, and the specific line or expression at fault.
2. A single fenced ```python block containing a complete pytest file. It must start
   with `from lru_cache import LRUCache`, use plain `assert`, and name each test
   after the defect it proves (for example `test_get_does_not_refresh_recency`).

Do not rewrite the module. Do not fix anything. Only find and prove defects.
Claim a defect only if your test demonstrates it - an unprovable claim is worse
than a missed one."""

REVISE_TEMPLATE = """You are the AUTHOR. Your module failed an independent review.

## Specification

{spec}

## Your current code

```python
{code}
```

## Confirmed defects - each one has a reproducing test that fails on your code

{findings}

---

Fix every confirmed defect. Do not change behaviour the review did not flag, and
do not rename anything in the public API.

Return the COMPLETE corrected contents of `lru_cache.py` as a single fenced
```python block, and nothing else."""


def run_model(model: str, prompt: str, timeout: int = 600):
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", model, "--format", "json", prompt],
        capture_output=True, text=True, timeout=timeout)
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
        raise RuntimeError(f"{model} failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return text, cost


def pytest_outcomes(module_src: Path, test_src: Path) -> tuple[set, set]:
    """Run test_src against module_src in isolation. Returns (all_tests, failed_tests)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy(module_src, work / "lru_cache.py")
        shutil.copy(test_src, work / "test_review.py")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_review.py", "-q", "--tb=no", "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True, timeout=300)
        out = proc.stdout + proc.stderr
        collect = subprocess.run(
            [sys.executable, "-m", "pytest", "test_review.py", "--collect-only", "-q",
             "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True, timeout=300)
    all_tests = {ln.split("::")[-1].strip() for ln in collect.stdout.splitlines()
                 if "::" in ln}
    failed = {m.split("::")[-1].strip()
              for m in re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.MULTILINE)}
    return all_tests, failed


def classify(all_tests: set, failed_flawed: set, failed_reference: set) -> dict:
    """CONFIRMED = fails on the flawed module AND passes on the correct one."""
    confirmed = sorted(failed_flawed - failed_reference)
    unfair = sorted(failed_flawed & failed_reference)      # fails on correct code too
    nothing = sorted(all_tests - failed_flawed)            # reproduced no defect
    return {"confirmed": confirmed, "unfair_tests": unfair, "no_defect_shown": nothing}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewer", required=True, choices=sorted(MODELS))
    ap.add_argument("--fixer", default="sonnet", choices=sorted(MODELS))
    ap.add_argument("--label", default=None)
    ap.add_argument("--no-revise", action="store_true")
    ap.add_argument("--timeout", type=int, default=900, help="per model call, seconds")
    ap.add_argument("--target", default="flawed", choices=["flawed", "reference"],
                    help="control condition: point the reviewer at the CORRECT code. "
                         "A good reviewer finds nothing; a confident one invents defects, "
                         "and the harness catches that.")
    args = ap.parse_args()

    label = args.label or args.reviewer
    outdir = HERE / "reviews" / label
    outdir.mkdir(parents=True, exist_ok=True)

    spec = (HERE / "SPEC.md").read_text()
    target = FLAWED if args.target == "flawed" else REFERENCE
    code = target.read_text()
    r_vendor, r_model = MODELS[args.reviewer]
    report = {"reviewer": {"key": args.reviewer, "vendor": r_vendor, "model": r_model}}

    # ---- 1. CRITIQUE -------------------------------------------------------
    print(f"\n[1/4] critique   {r_vendor} / {r_model.split('/')[-1]}")
    start = time.time()
    text, cost = run_model(r_model, REVIEW_TEMPLATE.format(spec=spec, code=code),
                           timeout=args.timeout)
    elapsed = time.time() - start
    (outdir / "review.md").write_text(text)
    blocks = CODE_BLOCK.findall(text)
    if not blocks:
        # A reviewer that finds nothing has nothing to prove. That is a clean bill
        # of health, not a failure - and on correct code it is the right answer.
        print("      no reproducing tests submitted - reviewer reported no defects")
        report["target"] = args.target
        report["validation"] = {"tests_submitted": 0, "confirmed": [],
                                "unfair_tests": [], "no_defect_shown": [],
                                "reviewer_reported_no_defects": True}
        (outdir / "report.json").write_text(json.dumps(report, indent=2))
        print(f"\n      report: {outdir / 'report.json'}")
        return 0
    test_file = outdir / "test_review.py"
    test_file.write_text(max(blocks, key=len))
    report["critique"] = {"cost_usd": cost, "elapsed_s": round(elapsed, 2),
                          "review_chars": len(text)}
    print(f"      wrote review.md + test_review.py   {elapsed:.1f}s  ${cost}")

    # ---- 2. VALIDATE THE FINDINGS -----------------------------------------
    print("[2/4] validate   running the reviewer's tests against flawed + reference")
    all_tests, failed_flawed = pytest_outcomes(target, test_file)
    _, failed_reference = pytest_outcomes(REFERENCE, test_file)
    verdict = classify(all_tests, failed_flawed, failed_reference)
    report["target"] = args.target
    report["validation"] = {"tests_submitted": len(all_tests), **verdict}
    if args.target == "reference":
        # Reviewing known-good code: every failing test is a false positive.
        report["validation"]["false_positives"] = sorted(failed_flawed)
    print(f"      {len(all_tests)} tests submitted   "
          f"CONFIRMED {len(verdict['confirmed'])}   "
          f"unfair {len(verdict['unfair_tests'])}   "
          f"no-defect {len(verdict['no_defect_shown'])}")
    for name in verdict["confirmed"]:
        print(f"        confirmed: {name}")
    for name in verdict["unfair_tests"]:
        print(f"        UNFAIR (fails on correct code too): {name}")

    if args.target == "reference":
        fp = sorted(failed_flawed)
        print(f"      CONTROL: reviewing known-good code. "
              f"{len(fp)} of {len(all_tests)} submitted tests fail on correct code "
              f"= false positives")
        for name in fp:
            print(f"        false positive: {name}")
        (outdir / "report.json").write_text(json.dumps(report, indent=2))
        print(f"\n      report: {outdir / 'report.json'}")
        return 0

    if args.no_revise or not verdict["confirmed"]:
        (outdir / "report.json").write_text(json.dumps(report, indent=2))
        print(f"\n      report: {outdir / 'report.json'}")
        return 0

    # ---- 3. REVISE ---------------------------------------------------------
    f_vendor, f_model = MODELS[args.fixer]
    findings = "\n".join(f"- `{n}` - see the reproducing test" for n in verdict["confirmed"])
    print(f"[3/4] revise     {f_vendor} / {f_model.split('/')[-1]}")
    start = time.time()
    text, cost = run_model(f_model, REVISE_TEMPLATE.format(spec=spec, code=code,
                                                           findings=findings),
                           timeout=args.timeout)
    elapsed = time.time() - start
    blocks = CODE_BLOCK.findall(text)
    if not blocks:
        print("      fixer returned no code block", file=sys.stderr)
        return 1
    fixed = outdir / "lru_cache_fixed.py"
    fixed.write_text(max(blocks, key=len))
    report["revision"] = {"fixer": args.fixer, "vendor": f_vendor, "model": f_model,
                          "cost_usd": cost, "elapsed_s": round(elapsed, 2)}
    print(f"      wrote lru_cache_fixed.py   {elapsed:.1f}s  ${cost}")

    # ---- 4. RE-VERIFY ------------------------------------------------------
    print("[4/4] re-verify  reviewer's tests + the hidden ground-truth suite")
    _, still_failing = pytest_outcomes(fixed, test_file)
    _, hidden_before = pytest_outcomes(FLAWED, HIDDEN)
    hidden_all, hidden_after = pytest_outcomes(fixed, HIDDEN)
    report["reverify"] = {
        "reviewer_tests_still_failing": sorted(still_failing),
        "hidden_total": len(hidden_all),
        "hidden_failing_before": sorted(hidden_before),
        "hidden_failing_after": sorted(hidden_after),
    }
    print(f"      reviewer tests still failing: {len(still_failing)}")
    print(f"      hidden suite: {len(hidden_before)} failing before -> "
          f"{len(hidden_after)} failing after  (of {len(hidden_all)})")

    report["total_cost_usd"] = round(
        (report["critique"]["cost_usd"] or 0) + (report["revision"]["cost_usd"] or 0), 6)
    (outdir / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\n      report: {outdir / 'report.json'}   total ${report['total_cost_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
