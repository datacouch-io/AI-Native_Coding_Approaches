#!/usr/bin/env python3
"""A 4-step coding pipeline whose model tier is chosen per step by a config file.

Steps: implement -> test -> refactor -> document. Which model runs which step is
the ONLY thing a config changes. The task, the prompts and the acceptance suite
are identical across configurations, so a cost difference between two runs is
attributable to the routing and nothing else.
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
ACCEPTANCE = HERE / "tests" / "test_acceptance.py"
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
MD_BLOCK = re.compile(r"```(?:markdown|md)?\s*\n(.*?)```", re.DOTALL)

# Appended when a config sets "prompt_style": "strict". Weaker tiers treat an
# instruction as an invitation to converse; this closes that door explicitly.
STRICT_SUFFIX = """

CRITICAL OUTPUT CONTRACT - you are running inside an automated pipeline with no
human to answer you:
- Do NOT ask questions. Do NOT propose options. Do NOT wait for confirmation.
- Do NOT explain what you plan to do.
- Your entire reply must be ONE fenced code block and nothing outside it.
If you are unsure about a choice, make the most reasonable one and proceed."""

MODELS = {
    "opus":   ("Anthropic", "amazon-bedrock/us.anthropic.claude-opus-5"),
    "sonnet": ("Anthropic", "amazon-bedrock/us.anthropic.claude-sonnet-5"),
    "haiku":  ("Anthropic", "amazon-bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "terra":  ("OpenAI",    "amazon-bedrock/global.openai.gpt-5.6-terra"),
    "sol":    ("OpenAI",    "amazon-bedrock/global.openai.gpt-5.6-sol"),
}

IMPLEMENT = """{spec}

You are the IMPLEMENTER. Write `durations.py` satisfying every numbered rule above.
You cannot create files. Return the COMPLETE module as a single fenced ```python
block and nothing else."""

TEST = """{spec}

Here is the implementation:

```python
{code}
```

You are the TEST AUTHOR. Write a pytest suite covering the contract, including the
error cases and the round-trip property. Import from `durations`. You cannot create
files. Return one fenced ```python block and nothing else."""

REFACTOR = """{spec}

Here is the current implementation:

```python
{code}
```

You are the REFACTORER. Improve clarity, naming and structure. Behaviour must not
change - every rule above must still hold exactly. Do not add features. You cannot
create files. Return the COMPLETE revised module as one fenced ```python block."""

DOCUMENT = """{spec}

Here is the final implementation:

```python
{code}
```

You are the TECHNICAL WRITER. Produce README documentation: a one-paragraph
overview, a usage section with short examples for both functions, and a table of
the accepted duration formats. Return one fenced markdown block and nothing else."""


def run_model(model_id: str, prompt: str, timeout: int):
    start = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
         "--model", model_id, "--format", "json", prompt],
        capture_output=True, text=True, timeout=timeout)
    elapsed = time.time() - start
    text, cost, tokens = "", None, {}
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "text":
            text += ev["part"].get("text", "")
        if ev.get("type") == "step_finish":
            cost = ev["part"].get("cost")
            tokens = ev["part"].get("tokens", {})
    if proc.returncode != 0 or not text.strip():
        raise RuntimeError(f"{model_id} failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return text, cost, elapsed, tokens


class BlockMissing(RuntimeError):
    """The model answered, but not in the format the pipeline needs."""


def block(text: str, markdown: bool = False) -> str:
    pattern = MD_BLOCK if markdown else CODE_BLOCK
    found = pattern.findall(text)
    if not found:
        raise BlockMissing("model returned no fenced block")
    return max(found, key=len)


def run_pytest(module: Path, test_file: Path) -> tuple[int, int, bool]:
    """Run a suite against a module in an isolated dir. Returns (passed, failed, collected)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy(module, work / "durations.py")
        shutil.copy(test_file, work / "test_suite.py")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_suite.py", "-q", "--tb=no",
             "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True, timeout=300)
        out = proc.stdout + proc.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    collected = "error during collection" not in out and "ImportError" not in out
    return passed, failed + errors, collected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--resume", action="store_true",
                    help="reuse implement/test artifacts already on disk")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    label, steps = cfg["label"], cfg["steps"]
    strict = cfg.get("prompt_style") == "strict"
    out = HERE / "runs" / label
    out.mkdir(parents=True, exist_ok=True)
    spec = (HERE / "SPEC.md").read_text()

    ledger = {"label": label, "config": steps,
              "prompt_style": "strict" if strict else "default", "steps": []}
    print(f"\n=== pipeline: {label} ===")
    print(f"{'step':<12}{'tier':<9}{'vendor':<11}{'model':<30}{'time':>8}{'cost':>13}")
    print("-" * 84)

    # Per-step artifacts are kept separately so a rerun can resume: `implement`
    # writes durations.impl.py, `refactor` consumes it and writes durations.py.
    impl_path = out / "durations.impl.py"
    tests_path = out / "test_generated.py"
    code, tests_src, docs = None, None, None
    failures = []

    for name in ("implement", "test", "refactor", "document"):
        tier = steps[name]
        vendor, model_id = MODELS[tier]

        if args.resume:
            if name == "implement" and impl_path.exists():
                code = impl_path.read_text()
                print(f"{name:<12}{'(reused ' + impl_path.name + ')':<60}")
                continue
            if name == "test" and tests_path.exists():
                tests_src = tests_path.read_text()
                print(f"{name:<12}{'(reused ' + tests_path.name + ')':<60}")
                continue
        if name == "implement":
            prompt = IMPLEMENT.format(spec=spec)
        elif name == "test":
            prompt = TEST.format(spec=spec, code=code)
        elif name == "refactor":
            prompt = REFACTOR.format(spec=spec, code=code)
        else:
            prompt = DOCUMENT.format(spec=spec, code=code)
        if strict:
            prompt += STRICT_SUFFIX

        text, cost, elapsed, tokens = run_model(model_id, prompt, args.timeout)
        (out / f"{name}.response.md").write_text(text)

        record = {"step": name, "tier": tier, "vendor": vendor, "model": model_id,
                  "cost_usd": cost, "elapsed_s": round(elapsed, 2),
                  "output_tokens": tokens.get("output"), "format_ok": True}
        try:
            if name == "document":
                docs = block(text, markdown=True)
                (out / "README.md").write_text(docs)
            elif name == "test":
                tests_src = block(text)
                tests_path.write_text(tests_src)
            elif name == "implement":
                code = block(text)
                impl_path.write_text(code)
                (out / "durations.py").write_text(code)
            else:
                code = block(text)
                (out / "durations.py").write_text(code)
        except BlockMissing:
            # A downgraded tier that stops honouring the output contract is a real
            # optimisation result, not a crash. Record it and carry on.
            record["format_ok"] = False
            failures.append(name)
            if name == "refactor":
                code = impl_path.read_text()          # keep the pre-refactor code
                (out / "durations.py").write_text(code)

        ledger["steps"].append(record)
        flag = "" if record["format_ok"] else "   <- NO FENCED BLOCK"
        print(f"{name:<12}{tier:<9}{vendor:<11}{model_id.split('/')[-1][:28]:<30}"
              f"{elapsed:>7.1f}s{'$' + format(cost or 0, '.4f'):>13}{flag}")

    module = out / "durations.py"
    acc_pass, acc_fail, acc_ok = run_pytest(module, ACCEPTANCE)
    gen_pass, gen_fail, gen_ok = run_pytest(module, out / "test_generated.py")

    ledger["acceptance"] = {"passed": acc_pass, "failed": acc_fail,
                            "collected": acc_ok, "green": acc_ok and acc_fail == 0}
    ledger["generated_tests"] = {"passed": gen_pass, "failed": gen_fail,
                                 "collected": gen_ok}
    ledger["total_cost_usd"] = round(sum(s["cost_usd"] or 0 for s in ledger["steps"]), 6)
    ledger["total_elapsed_s"] = round(sum(s["elapsed_s"] for s in ledger["steps"]), 2)
    ledger["readme_chars"] = len(docs or "")
    ledger["format_failures"] = failures
    (out / "ledger.json").write_text(json.dumps(ledger, indent=2))

    print("-" * 84)
    print(f"{'TOTAL':<12}{'':<50}{ledger['total_elapsed_s']:>7.1f}s"
          f"{'$' + format(ledger['total_cost_usd'], '.4f'):>13}")
    print(f"\n  acceptance suite : {acc_pass} passed, {acc_fail} failed"
          f"   -> {'GREEN' if ledger['acceptance']['green'] else 'RED'}")
    print(f"  model-written    : {gen_pass} passed, {gen_fail} failed")
    print(f"  README           : {ledger['readme_chars']} chars")
    if failures:
        print(f"  FORMAT FAILURES  : {', '.join(failures)} "
              f"- see runs/{label}/<step>.response.md")
    print(f"  ledger           : {out / 'ledger.json'}")
    return 0 if ledger["acceptance"]["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
