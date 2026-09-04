#!/usr/bin/env python3
"""Exercise every model's p1 rate limiter against one behavioural contract.

The contract (same for all four): with capacity=5 and a 2 tokens/second refill,
the first 5 requests are allowed, the 6th is rejected, and after ~1.1s of refill
a further request is allowed again.

Each model invented a different API for the same algorithm, so each entry below
records how to construct and call it. Writing this table IS the exercise: the
edit cost captured here is the real, rarely-measured price of switching models.
"""
import importlib
import sys
import time
from pathlib import Path

CODE_DIR = Path("artifacts/lab-1/code/p1-rate-limiter")

# module, class, constructor kwargs, method, extra args
CASES = [
    ("claude_sonnet_5", "TokenBucket",            dict(capacity=5, refill_rate=2), "consume", ()),
    ("claude_opus_5",   "TokenBucket",            dict(capacity=5, rate=2),        "consume", ()),
    ("gpt_5_6_sol",     "TokenBucket",            dict(capacity=5, refill_rate=2), "consume", ()),
    ("gpt_5_6_terra",   "TokenBucketRateLimiter", dict(rate=2, capacity=5),        "allow",   ("k",)),
]


def allowed(result) -> bool:
    """Normalise four different return shapes into one boolean."""
    if isinstance(result, tuple):        # gpt-5.6-sol -> (bool, retry_after)
        return bool(result[0])
    if hasattr(result, "allowed"):       # claude-opus-5 -> Decision dataclass
        return bool(result.allowed)
    return bool(result)                  # sonnet / terra -> plain bool


def main() -> int:
    if not CODE_DIR.exists():
        print(f"ERROR: {CODE_DIR} not found - run tools/extract_responses.py first",
              file=sys.stderr)
        return 1
    sys.path.insert(0, str(CODE_DIR.resolve()))

    print(f"{'model':<18}{'verdict':<9}{'returns':<12}burst  reject  refill")
    print("-" * 62)
    failures = 0
    for mod_name, cls_name, kwargs, method, extra in CASES:
        try:
            cls = getattr(importlib.import_module(mod_name), cls_name)
            bucket = cls(**kwargs)
            call = getattr(bucket, method)

            first = call(*extra)
            returns = type(first).__name__
            decisions = [allowed(first)] + [allowed(call(*extra)) for _ in range(6)]

            burst = decisions[:5] == [True] * 5
            reject = decisions[5] is False
            time.sleep(1.1)
            refill = allowed(call(*extra))

            ok = burst and reject and refill
            failures += 0 if ok else 1
            print(f"{mod_name:<18}{'PASS' if ok else 'FAIL':<9}{returns:<12}"
                  f"{str(burst):<7}{str(reject):<8}{refill}")
        except ModuleNotFoundError as e:
            failures += 1
            print(f"{mod_name:<18}{'ERROR':<9}missing dependency: {e.name} "
                  f"(this model coupled its answer to a web framework)")
        except Exception as e:
            failures += 1
            print(f"{mod_name:<18}{'ERROR':<9}{type(e).__name__}: {e}")

    print("-" * 62)
    print(f"{len(CASES) - failures}/{len(CASES)} implementations satisfy the contract")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
