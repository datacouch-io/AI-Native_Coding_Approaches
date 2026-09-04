import json
import subprocess
import time
from pathlib import Path

MODELS = [
    ("claude-sonnet-5", "amazon-bedrock/us.anthropic.claude-sonnet-5"),
    ("claude-opus-5", "amazon-bedrock/us.anthropic.claude-opus-5"),
    ("gpt-5.6-sol", "amazon-bedrock/global.openai.gpt-5.6-sol"),
    ("gpt-5.6-terra", "amazon-bedrock/global.openai.gpt-5.6-terra"),
]

PROMPTS = [
    ("p1-rate-limiter", "prompts/p1-rate-limiter.txt"),
    ("p2-refactor", "prompts/p2-refactor.txt"),
    ("p3-caching-layer", "prompts/p3-caching-layer.txt"),
    ("p4-unit-tests", "prompts/p4-unit-tests.txt"),
]

OUT_DIR = Path("artifacts/lab-1/runs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

for model_name, model_id in MODELS:
    for prompt_name, prompt_path in PROMPTS:
        prompt_text = Path(prompt_path).read_text()
        out_file = OUT_DIR / f"{model_name}__{prompt_name}.jsonl"
        print(f"=== {model_name} / {prompt_name} ===", flush=True)

        start = time.time()
        proc = subprocess.run(
            ["opencode", "run", "--agent", "plan", "--model", model_id, "--format", "json", prompt_text],
            capture_output=True, text=True, timeout=180,
        )
        wall_clock = time.time() - start

        out_file.write_text(proc.stdout)
        if proc.returncode != 0:
            print(f"  FAILED (exit {proc.returncode}): {proc.stderr[:300]}")
            results.append({
                "model": model_name, "prompt": prompt_name, "wall_clock_s": round(wall_clock, 3),
                "status": "FAILED", "error": proc.stderr[:500],
            })
            continue

        text = ""
        tokens = {}
        cost = None
        for line in proc.stdout.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "text":
                text += d["part"].get("text", "")
            if d.get("type") == "step_finish":
                tokens = d["part"].get("tokens", {})
                cost = d["part"].get("cost")

        results.append({
            "model": model_name, "prompt": prompt_name, "wall_clock_s": round(wall_clock, 3),
            "status": "OK", "cost_usd": cost, "tokens": tokens,
            "response_chars": len(text),
        })
        print(f"  OK  wall_clock={wall_clock:.2f}s  cost=${cost}  tokens={tokens}", flush=True)

Path("artifacts/lab-1/benchmark_results.json").write_text(json.dumps(results, indent=2))
print("\nDone. Results in artifacts/lab-1/benchmark_results.json")
