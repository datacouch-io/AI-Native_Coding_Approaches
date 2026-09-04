#!/usr/bin/env python3
"""Turn raw OpenCode JSONL runs into readable responses + runnable code files.

Reads:  artifacts/lab-1/runs/<model>__<prompt>.jsonl
Writes: artifacts/lab-1/responses/<model>__<prompt>.md   (full response text)
        artifacts/lab-1/code/<prompt>/<model>.py         (first Python code block)
"""
import json
import re
import sys
from pathlib import Path

RUNS = Path("artifacts/lab-1/runs")
RESPONSES = Path("artifacts/lab-1/responses")
CODE = Path("artifacts/lab-1/code")

CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def response_text(jsonl_path: Path) -> str:
    """Concatenate every `text` event in an OpenCode --format json run."""
    out = []
    for line in jsonl_path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            out.append(event["part"].get("text", ""))
    return "".join(out)


def main() -> int:
    if not RUNS.exists():
        print(f"ERROR: {RUNS} not found - run run_benchmark.py first", file=sys.stderr)
        return 1

    RESPONSES.mkdir(parents=True, exist_ok=True)
    CODE.mkdir(parents=True, exist_ok=True)

    files = sorted(RUNS.glob("*.jsonl"))
    if not files:
        print(f"ERROR: no .jsonl runs in {RUNS}", file=sys.stderr)
        return 1

    extracted = 0
    for jsonl in files:
        model, prompt = jsonl.stem.split("__", 1)
        text = response_text(jsonl)
        (RESPONSES / f"{model}__{prompt}.md").write_text(text)

        blocks = CODE_BLOCK.findall(text)
        if blocks:
            target_dir = CODE / prompt
            target_dir.mkdir(parents=True, exist_ok=True)
            # longest block = the real implementation, not a usage snippet
            best = max(blocks, key=len)
            safe = model.replace("-", "_").replace(".", "_")
            (target_dir / f"{safe}.py").write_text(best)
            extracted += 1
        print(f"{jsonl.stem:<40} {len(text):>6} chars  {len(blocks)} code block(s)")

    print(f"\nWrote {len(files)} responses to {RESPONSES}/")
    print(f"Wrote {extracted} code files to {CODE}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
