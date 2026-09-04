#!/usr/bin/env python3
"""Run one coding task across three model handoffs, under different context strategies.

Every hop is a SEPARATE `opencode run`, so each model genuinely starts with an
empty context. That is the real-world situation this lab is about: a new session,
often a different model, with no memory of what was decided earlier.

Strategies:
  isolated    each hop sees only TASK.md            -> the models invent conflicting APIs
  contract    hops also see CONTRACT.md + STATE.md  -> compact, structured handoff
  full        hops also see CONTRACT.md + the ENTIRE implementation source

`contract` and `full` should both work. The difference between them is what they
cost you in input tokens - which is the "context window efficiency" half of this lab.
"""
import argparse
import ast
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = (HERE / "TASK.md").read_text()

# An empty working directory. `--agent plan` can still READ files, so pointing a hop
# at the lab folder would let it read CONTRACT.md (or another run's output) straight
# off disk - which would silently invalidate the isolated condition. Everything a
# model is allowed to know must arrive in its prompt, and nowhere else.
SANDBOX = HERE / ".sandbox"

# Hop 1 is identical under every strategy, so it is generated once and reused. That
# keeps the comparison honest: only the HANDOFF differs between runs, not the design.
SHARED = HERE / "runs" / "_shared"

OPUS   = "amazon-bedrock/us.anthropic.claude-opus-5"
SONNET = "amazon-bedrock/us.anthropic.claude-sonnet-5"
TERRA  = "amazon-bedrock/global.openai.gpt-5.6-terra"

CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def run_model(model: str, prompt: str, timeout: int = 300):
    """One fresh opencode session. Returns (text, cost, tokens, elapsed)."""
    cmd = ["opencode", "run", "--dir", str(SANDBOX), "--agent", "plan",
           "--model", model, "--format", "json", prompt]
    start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
        raise RuntimeError(f"{model} failed (exit {proc.returncode}): {proc.stderr[:300]}")
    return text, cost, tokens, elapsed


def biggest_code_block(text: str) -> str:
    blocks = CODE_BLOCK.findall(text)
    if not blocks:
        raise RuntimeError("model returned no fenced code block")
    return max(blocks, key=len)


def public_api(source: str) -> str:
    """Deterministically summarise a module's public API - no model call needed.

    This is the compact handoff artifact. It is generated from the code that was
    actually written, so it cannot drift from reality the way prose notes do.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"(could not parse implementation: {e})"

    lines = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            lines.append(f"def {node.name}({ast.unparse(node.args)})"
                         + (f" -> {ast.unparse(node.returns)}" if node.returns else ""))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            lines.append(f"class {node.name}({bases}):" if bases else f"class {node.name}:")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                    lines.append(f"    def {sub.name}({ast.unparse(sub.args)})"
                                 + (f" -> {ast.unparse(sub.returns)}" if sub.returns else ""))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    lines.append(f"{t.id} = ...")
    return "\n".join(lines) if lines else "(no public API found)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=["isolated", "contract", "full"])
    ap.add_argument("--out", required=True, help="output directory for this run")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = {"strategy": args.strategy, "hops": []}

    def record(name, model, cost, tokens, elapsed, prompt):
        ledger["hops"].append({
            "hop": name, "model": model.split("/")[-1],
            "prompt_chars": len(prompt),
            "input_tokens": tokens.get("input"), "output_tokens": tokens.get("output"),
            "cache_read": (tokens.get("cache") or {}).get("read"),
            "cost_usd": cost, "elapsed_s": round(elapsed, 2),
        })
        print(f"  {name:<10} {model.split('/')[-1]:<28} {elapsed:6.1f}s  "
              f"${cost}  prompt={len(prompt)} chars")

    print(f"\n=== strategy: {args.strategy} -> {out} ===")

    # ---- hop 1: DESIGN (identical in every strategy) -------------------------
    design_prompt = (
        f"{TASK}\n\n"
        "You are the DESIGNER. Do not write the implementation.\n"
        "Produce a precise API contract another engineer will implement against: "
        "exact function names, full signatures with type hints, return shapes, "
        "the exception types raised and when, and how rounding and mixed currencies "
        "are handled. Be specific enough that two engineers working separately would "
        "produce interchangeable code. Return the contract as markdown."
    )
    SHARED.mkdir(parents=True, exist_ok=True)
    shared_contract = SHARED / "CONTRACT.md"
    if shared_contract.exists():
        contract = shared_contract.read_text()
        print(f"  {'design':<10} (reused {shared_contract.relative_to(HERE)}"
              f" - hop 1 is identical under every strategy)")
    else:
        contract, cost, tokens, elapsed = run_model(OPUS, design_prompt)
        shared_contract.write_text(contract)
        record("design", OPUS, cost, tokens, elapsed, design_prompt)
    (out / "CONTRACT.md").write_text(contract)

    # ---- hop 2: IMPLEMENT ---------------------------------------------------
    impl_prompt = f"{TASK}\n\nYou are the IMPLEMENTER. Write `expenses.py`."
    if args.strategy in ("contract", "full"):
        impl_prompt = (
            f"{TASK}\n\n"
            f"You are the IMPLEMENTER. Another engineer has already agreed this API "
            f"contract. Follow it EXACTLY - do not rename anything or change any "
            f"signature:\n\n---\n{contract}\n---\n\n"
            f"Write `expenses.py` implementing that contract."
        )
    impl_prompt += ("\n\nYou cannot create files. Return the COMPLETE contents of "
                    "expenses.py as a single fenced ```python code block, and nothing "
                    "else. Do not describe your approach first.")
    text, cost, tokens, elapsed = run_model(SONNET, impl_prompt)
    (out / "implement.response.md").write_text(text)
    impl_src = biggest_code_block(text)
    (out / "expenses.py").write_text(impl_src)
    record("implement", SONNET, cost, tokens, elapsed, impl_prompt)

    # compact, generated-from-reality handoff artifact
    state = (f"# Handoff state\n\n## Public API of expenses.py (extracted from the code)\n\n"
             f"```python\n{public_api(impl_src)}\n```\n")
    (out / "STATE.md").write_text(state)

    # ---- hop 3: TEST (a different vendor entirely) --------------------------
    test_prompt = f"{TASK}\n\nYou are the TEST AUTHOR. Write `test_expenses.py`."
    if args.strategy == "contract":
        test_prompt = (
            f"{TASK}\n\nYou are the TEST AUTHOR. The module has already been built "
            f"against this agreed contract:\n\n---\n{contract}\n---\n\n"
            f"And this is the public API that actually exists in `expenses.py`:\n\n"
            f"---\n{state}\n---\n\n"
            f"Write `test_expenses.py` using ONLY those names and signatures."
        )
    elif args.strategy == "full":
        test_prompt = (
            f"{TASK}\n\nYou are the TEST AUTHOR. The module has already been built "
            f"against this agreed contract:\n\n---\n{contract}\n---\n\n"
            f"Here is the complete implementation source:\n\n"
            f"---\n```python\n{impl_src}\n```\n---\n\n"
            f"Write `test_expenses.py` using ONLY the names and signatures it defines."
        )
    test_prompt += ("\n\nUse pytest and import from `expenses`. You cannot create files. "
                    "Return the COMPLETE contents of test_expenses.py as a single fenced "
                    "```python code block, and nothing else.")
    text, cost, tokens, elapsed = run_model(TERRA, test_prompt)
    (out / "test.response.md").write_text(text)
    (out / "test_expenses.py").write_text(biggest_code_block(text))
    record("test", TERRA, cost, tokens, elapsed, test_prompt)

    ledger["total_cost_usd"] = round(sum(h["cost_usd"] or 0 for h in ledger["hops"]), 6)
    ledger["total_input_tokens"] = sum(h["input_tokens"] or 0 for h in ledger["hops"])
    (out / "ledger.json").write_text(json.dumps(ledger, indent=2))
    print(f"  total: ${ledger['total_cost_usd']}  input_tokens={ledger['total_input_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
