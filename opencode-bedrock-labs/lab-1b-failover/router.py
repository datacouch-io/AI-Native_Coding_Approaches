#!/usr/bin/env python3
"""Cross-vendor failover router for OpenCode + Bedrock.

Runs a coding task against a PRIMARY model. If that call fails in a way that is
worth retrying elsewhere, it re-routes the identical task to a FALLBACK model
from a DIFFERENT vendor, and reports which one actually delivered the answer.

Fault injection is real, not simulated in-process: `--fault` starts a local HTTP
endpoint that returns Bedrock-shaped errors and points the primary's OpenCode
config at it via `provider.amazon-bedrock.options.baseURL`. The primary then
fails exactly the way it would during a genuine provider incident - at the HTTP
layer, inside the AWS SDK, after OpenCode's own internal retries are exhausted.

Usage:
  python3 router.py --prompt-file prompt.txt
  python3 router.py --prompt-file prompt.txt --fault throttle
  python3 router.py --prompt-file prompt.txt --fault throttle --no-failover
  python3 router.py --prompt-file prompt.txt --fault client-error
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTHY = HERE / "configs" / "healthy"
FAULTED = HERE / "configs" / "faulted"
MOCK = HERE / "mock_outage.py"
MOCK_PORT = 8099

# Routing table. Order matters: the first entry is the primary. The fallback is
# deliberately a DIFFERENT VENDOR - a second Anthropic model would not survive an
# Anthropic-wide incident, which is the whole point of the exercise.
ROUTES = [
    {"role": "primary",  "vendor": "Anthropic",
     "model": "amazon-bedrock/us.anthropic.claude-sonnet-5"},
    {"role": "fallback", "vendor": "OpenAI",
     "model": "amazon-bedrock/global.openai.gpt-5.6-terra"},
]

# Which failure classes justify re-routing to another vendor. A 4xx that is not
# 429 means WE sent a bad request; failing over on that would just run the same
# broken request against a second provider and hide the bug.
FAILOVER_WORTHY = {"rate_limited", "provider_unavailable", "provider_error", "timeout",
                   "connection_refused"}


def extract_error(stdout: str) -> dict:
    """Pull OpenCode's structured error event out of a --format json stream.

    In JSON mode OpenCode writes failures as {"type":"error", ...} on STDOUT and
    leaves stderr empty, so string-matching stderr finds nothing.
    """
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            return (event.get("error") or {}).get("data") or {}
    return {}


def classify(err: dict, stderr: str, timed_out: bool) -> tuple[str, str]:
    """Return (error_class, human_message) from the structured error where possible."""
    if timed_out:
        return "timeout", "client gave up waiting for the provider"

    status = err.get("statusCode")
    message = err.get("message") or stderr.strip().splitlines()[-1:] or ["(no error text)"]
    message = message if isinstance(message, str) else message[0]

    # Bedrock puts its own exception name in the response body - the most precise signal.
    body_type = ""
    try:
        body_type = json.loads(err.get("responseBody", "{}")).get("__type", "")
    except (json.JSONDecodeError, TypeError):
        pass

    if status == 429 or "Throttling" in body_type:
        return "rate_limited", message
    if isinstance(status, int) and 500 <= status < 600:
        return "provider_unavailable", message
    if isinstance(status, int) and 400 <= status < 500:
        return "client_error", message
    if err.get("isRetryable") is True:
        return "provider_error", message
    if "ECONNREFUSED" in stderr or "fetch failed" in stderr:
        return "connection_refused", message
    return "unknown_error", message


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def start_mock(mode: str):
    proc = subprocess.Popen([sys.executable, str(MOCK), mode, str(MOCK_PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_for_port(MOCK_PORT):
        proc.kill()
        raise RuntimeError(f"mock outage endpoint did not come up on :{MOCK_PORT}")
    print(f"  [fault] mock outage endpoint up on :{MOCK_PORT} mode={mode}")
    return proc


def call_model(model: str, config_dir: Path, prompt: str, timeout: int,
               raw_dir: Path = None, tag: str = ""):
    """One attempt against one model. Never leaves an orphaned child behind."""
    cmd = ["opencode", "run", "--dir", str(config_dir), "--agent", "plan",
           "--model", model, "--format", "json", prompt]
    start = time.time()
    timed_out = False

    # start_new_session so a timeout can kill the whole process group: OpenCode
    # spawns a local server child that otherwise keeps the pipes open and hangs.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        code = -1
    elapsed = time.time() - start

    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{tag}.stdout.jsonl").write_text(stdout or "")
        (raw_dir / f"{tag}.stderr.txt").write_text(stderr or "")

    text, cost = "", None
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text += event["part"].get("text", "")
        if event.get("type") == "step_finish":
            cost = event["part"].get("cost")

    ok = code == 0 and bool(text.strip())
    return ok, text, cost, stdout or "", stderr or "", elapsed, timed_out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--fault",
                    choices=["none", "throttle", "server-error", "client-error", "timeout"],
                    default="none", help="inject a real HTTP-level failure on the primary")
    ap.add_argument("--no-failover", action="store_true",
                    help="baseline: try only the primary, so you can watch the task fail")
    ap.add_argument("--timeout", type=int, default=120, help="per-attempt timeout (s)")
    ap.add_argument("--trace-out", default=None)
    args = ap.parse_args()

    for var in ("AWS_REGION", "AWS_PROFILE"):
        if not os.environ.get(var):
            print(f"ERROR: {var} is not set - see the lab's setup section", file=sys.stderr)
            return 2

    prompt = Path(args.prompt_file).read_text().strip()
    routes = ROUTES[:1] if args.no_failover else ROUTES
    raw_dir = (Path(args.trace_out).parent / "raw") if args.trace_out else None

    trace = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fault_injected": args.fault,
        "failover_enabled": not args.no_failover,
        "attempts": [],
    }

    print(f"\nTask:  {prompt[:68]}{'...' if len(prompt) > 68 else ''}")
    print(f"Fault: {args.fault}    Failover: {'ON' if not args.no_failover else 'OFF'}\n")

    mock = start_mock(args.fault) if args.fault != "none" else None
    delivered_by, answer, halt_reason = None, "", None

    try:
        for route in routes:
            faulted = args.fault != "none" and route["role"] == "primary"
            config_dir = FAULTED if faulted else HEALTHY

            print(f"-> [{route['role']}] {route['vendor']} | {route['model'].split('/')[-1]}"
                  f"{'   (endpoint faulted)' if faulted else ''}")

            ok, text, cost, stdout, stderr, elapsed, timed_out = call_model(
                route["model"], config_dir, prompt, args.timeout,
                raw_dir=raw_dir, tag=route["role"])

            attempt = {
                "role": route["role"], "vendor": route["vendor"], "model": route["model"],
                "endpoint": "faulted-mock" if faulted else "aws-bedrock",
                "outcome": "success" if ok else "failure",
                "elapsed_s": round(elapsed, 2), "cost_usd": cost,
            }

            if ok:
                attempt["response_chars"] = len(text)
                trace["attempts"].append(attempt)
                print(f"   OK   succeeded in {elapsed:.1f}s  cost=${cost}  ({len(text)} chars)\n")
                delivered_by, answer = route, text
                break

            err = extract_error(stdout)
            error_class, message = classify(err, stderr, timed_out)
            attempt.update({
                "error_class": error_class,
                "status_code": err.get("statusCode"),
                "provider_retryable": err.get("isRetryable"),
                "error": message[:300],
            })
            trace["attempts"].append(attempt)

            print(f"   FAIL failed in {elapsed:.1f}s  [{error_class}]")
            if err.get("statusCode"):
                print(f"        HTTP {err['statusCode']}  provider says retryable="
                      f"{err.get('isRetryable')}")
            print(f"        {message[:110]}")

            if error_class not in FAILOVER_WORTHY:
                halt_reason = (f"{error_class} is not failover-worthy - this is a fault in OUR "
                               f"request, not the provider. Re-routing would hide the bug.")
                print(f"   STOP {halt_reason}\n")
                break
            print("   ->   re-routing to the next provider\n"
                  if route is not routes[-1] else "   ->   no routes left\n")
    finally:
        if mock:
            mock.terminate()
            try:
                mock.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mock.kill()

    trace["delivered"] = bool(delivered_by)
    trace["delivered_by"] = delivered_by["model"] if delivered_by else None
    trace["delivered_by_vendor"] = delivered_by["vendor"] if delivered_by else None
    if halt_reason:
        trace["halted_because"] = halt_reason

    line = "-" * 70
    print(line)
    if delivered_by:
        print(f"TASK COMPLETED - delivered by {delivered_by['vendor']} "
              f"({delivered_by['model'].split('/')[-1]}) after {len(trace['attempts'])} attempt(s)")
        print(line)
        print(answer.strip()[:500])
    else:
        print(f"TASK FAILED - {len(trace['attempts'])} attempt(s), no answer produced")
        if halt_reason:
            print(f"reason: {halt_reason}")
    print(line)

    if args.trace_out:
        out = Path(args.trace_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(trace, indent=2))
        print(f"trace written to {out}")

    return 0 if delivered_by else 1


if __name__ == "__main__":
    raise SystemExit(main())
