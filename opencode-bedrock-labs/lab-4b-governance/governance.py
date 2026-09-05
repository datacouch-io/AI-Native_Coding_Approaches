#!/usr/bin/env python3
"""A policy gate in front of Bedrock, and a test of whether AWS agrees with it.

Two independent layers are exercised here, and the difference between them is the
point of the lab:

  LAYER 1 - the client-side gate (this file). Classifies the payload, checks the
            policy, and refuses non-compliant routing BEFORE any request is sent.
            Fast, cheap, auditable - and it is your own code, so it is only as
            trustworthy as the process that stops someone bypassing it.

  LAYER 2 - AWS itself. A `us.` inference profile simply does not exist in an EU
            region. That denial is enforced by the platform whether or not your
            gate ran, and it is what makes the control real rather than advisory.
"""
import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "configs" / "policy.json").read_text())
AUDIT = HERE / "runs" / "audit-log.jsonl"


def classify(text: str) -> str:
    """Lowest-privilege wins: any PII signal classifies the whole payload as PII."""
    for pattern in POLICY["detectors"]["pii"]:
        if re.search(pattern, text):
            return "pii"
    return "internal"


def evaluate(classification: str, endpoint: str) -> tuple[bool, str]:
    """Layer 1. Returns (allowed, reason)."""
    rule = POLICY["classifications"].get(classification)
    if rule is None:
        return False, f"unknown classification {classification!r}"
    ep = POLICY["endpoints"].get(endpoint)
    if ep is None:
        return False, f"endpoint {endpoint!r} is not in the approved inventory"
    if ep["residency"] not in rule["allowed_residency"]:
        return False, (f"{classification} data may only be processed in "
                       f"{'/'.join(rule['allowed_residency'])}; "
                       f"{endpoint} is {ep['residency']}")
    if rule["requires_baa"] and not ep["baa"]:
        return False, f"{classification} data requires a BAA-covered endpoint; {endpoint} has none"
    return True, f"{classification} permitted on {ep['residency']} endpoint {endpoint}"


def audit(record: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    record["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record["policy_version"] = POLICY["policy_version"]
    with AUDIT.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def call_bedrock(endpoint: str, region: str, text: str, timeout: int = 120):
    """Layer 2. A direct Converse call - no client-side checks in the way."""
    start = time.time()
    proc = subprocess.run(
        ["aws", "bedrock-runtime", "converse", "--region", region,
         "--model-id", endpoint,
         "--messages", json.dumps([{"role": "user", "content": [{"text": text}]}]),
         "--inference-config", json.dumps({"maxTokens": 16})],
        capture_output=True, text=True, timeout=timeout)
    elapsed = time.time() - start
    if proc.returncode == 0:
        return True, "responded", round(elapsed, 2)
    err = proc.stderr.strip()
    kind = next((k for k in ("AccessDeniedException", "ValidationException",
                             "ResourceNotFoundException", "ThrottlingException")
                 if k in err), "Error")
    return False, kind, round(elapsed, 2)


SCENARIOS = [
    ("S1", "internal", "Refactor this function for readability: def f(a,b): return a+b",
     "us.anthropic.claude-sonnet-5"),
    ("S2", "pii", "Fix the bug in this record handler. Sample row: "
                  "patient jane.doe@example.com, DOB 1984-03-02, SSN 123-45-6789",
     "us.anthropic.claude-sonnet-5"),
    ("S3", "pii", "Fix the bug in this record handler. Sample row: "
                  "patient jane.doe@example.com, DOB 1984-03-02, SSN 123-45-6789",
     "eu.anthropic.claude-sonnet-5"),
    ("S4", "internal", "Summarise our deployment runbook structure.",
     "global.openai.gpt-5.6-terra"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="also send the ALLOWED requests to Bedrock for real")
    ap.add_argument("--bypass-test", action="store_true",
                    help="skip the gate and call AWS directly, to prove layer 2 stands alone")
    args = ap.parse_args()

    if args.bypass_test:
        print("\nLAYER 2 ONLY - the client gate is bypassed entirely.")
        print("If AWS does not enforce residency, a bypassed gate means no control at all.\n")
        print(f"  {'endpoint':<34}{'region':<15}{'result':<40}time")
        print("  " + "-" * 94)
        for endpoint, region in (("us.anthropic.claude-sonnet-5", "us-east-1"),
                                 ("us.anthropic.claude-sonnet-5", "eu-central-1"),
                                 ("eu.anthropic.claude-sonnet-5", "eu-central-1")):
            ok, kind, elapsed = call_bedrock(endpoint, region, "hi")
            verdict = "ALLOWED" if ok else f"BLOCKED BY AWS ({kind})"
            print(f"  {endpoint:<34}{region:<15}{verdict:<40}{elapsed}s")
            audit({"layer": 2, "endpoint": endpoint, "region": region,
                   "allowed": ok, "detail": kind})
        return 0

    print(f"\npolicy {POLICY['policy_version']}   "
          f"{len(POLICY['endpoints'])} approved endpoints   "
          f"{len(POLICY['classifications'])} classifications\n")
    print(f"  {'':<4}{'declared':<10}{'detected':<10}{'endpoint':<34}{'gate':<10}reason")
    print("  " + "-" * 108)

    blocked = allowed = 0
    for sid, declared, text, endpoint in SCENARIOS:
        detected = classify(text)
        ok, reason = evaluate(detected, endpoint)
        gate = "ALLOW" if ok else "BLOCK"
        blocked += not ok
        allowed += ok
        print(f"  {sid:<4}{declared:<10}{detected:<10}{endpoint:<34}{gate:<10}{reason}")
        record = {"layer": 1, "scenario": sid, "declared": declared, "detected": detected,
                  "endpoint": endpoint, "allowed": ok, "reason": reason}

        if ok and args.live:
            region = POLICY["endpoints"][endpoint]["region"]
            sent_ok, kind, elapsed = call_bedrock(endpoint, region, text)
            record["sent"] = True
            record["bedrock_result"] = kind
            print(f"  {'':<58}-> sent to {region}: {kind} ({elapsed}s)")
        else:
            record["sent"] = False
        audit(record)

    print("  " + "-" * 108)
    print(f"  {allowed} allowed, {blocked} blocked by policy   "
          f"audit trail -> {AUDIT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
