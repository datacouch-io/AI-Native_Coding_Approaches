Here's a production-shaped token bucket limiter. Two parts: the core algorithm + in-process store, then a FastAPI/ASGI hookup and a Redis variant for multi-worker deployments.

## Core: token bucket

```python
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int          # bucket capacity (burst size)
    remaining: int      # tokens left after this call
    retry_after: float  # seconds until `cost` tokens are available (0 if allowed)
    reset_after: float  # seconds until the bucket is completely full


class TokenBucket:
    """Single bucket. Refills lazily, so there is no background timer."""

    __slots__ = ("capacity", "rate", "_tokens", "_updated")

    def __init__(self, capacity: float, rate: float, *, now: float | None = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if rate <= 0:
            raise ValueError("rate must be > 0 (tokens per second)")
        self.capacity = float(capacity)
        self.rate = float(rate)
        self._tokens = float(capacity)          # start full: allow an initial burst
        self._updated = time.monotonic() if now is None else now

    @property
    def is_full(self) -> bool:
        return self._tokens >= self.capacity

    def _refill(self, now: float) -> None:
        # monotonic clock => immune to NTP steps / DST
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now

    def consume(self, cost: float = 1.0, *, now: float | None = None) -> Decision:
        if cost <= 0:
            raise ValueError("cost must be > 0")
        if cost > self.capacity:
            # Otherwise the caller would wait forever.
            raise ValueError(f"cost {cost} exceeds capacity {self.capacity}")

        now = time.monotonic() if now is None else now
        self._refill(now)

        if self._tokens >= cost:
            self._tokens -= cost
            retry_after = 0.0
            allowed = True
        else:
            retry_after = (cost - self._tokens) / self.rate
            allowed = False

        return Decision(
            allowed=allowed,
            limit=int(self.capacity),
            remaining=int(self._tokens),  # floor: never over-promise
            retry_after=retry_after,
            reset_after=(self.capacity - self._tokens) / self.rate,
        )
```

## Keyed store (per client/route), thread-safe with GC

```python
class RateLimiter:
    """Per-key token buckets with lazy eviction of idle keys.

    capacity = burst allowance, rate = sustained requests/second.
    e.g. capacity=20, rate=5  ->  5 rps sustained, bursts up to 20.
    """

    def __init__(self, capacity: float, rate: float, *, idle_ttl: float = 300.0) -> None:
        self._capacity = capacity
        self._rate = rate
        self._idle_ttl = idle_ttl
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._next_sweep = time.monotonic() + idle_ttl

    def check(self, key: str, cost: float = 1.0) -> Decision:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(self._capacity, self._rate, now=now)
                self._buckets[key] = bucket
            decision = bucket.consume(cost, now=now)
            if now >= self._next_sweep:
                self._sweep(now)
            return decision

    def _sweep(self, now: float) -> None:
        # Called under lock. A full bucket carries no state worth keeping.
        stale = [k for k, b in self._buckets.items()
                 if b.is_full and now - b._updated > self._idle_ttl]
        for k in stale:
            del self._buckets[k]
        self._next_sweep = now + self._idle_ttl
```

Notes on the store:
- One global lock is fine up to roughly 10⁵ checks/sec; if it becomes hot, shard into N sub-dicts keyed by `hash(key) % N`, each with its own lock.
- Eviction matters: without it, an unauthenticated endpoint keyed by IP is an unbounded memory leak.
- `asyncio` single-threaded servers don't need the lock, but keeping it costs ~100ns and makes the class safe under thread-pool workers (gunicorn `gthread`, WSGI).

## FastAPI / Starlette middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

limiter = RateLimiter(capacity=20, rate=5)  # 5 rps sustained, burst 20


def client_key(request: Request) -> str:
    # Prefer an authenticated identity; fall back to IP.
    # Only trust X-Forwarded-For if a proxy you control sets it.
    if (user := getattr(request.state, "user_id", None)):
        return f"user:{user}"
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        d = limiter.check(client_key(request))
        headers = {
            "RateLimit-Limit": str(d.limit),
            "RateLimit-Remaining": str(d.remaining),
            "RateLimit-Reset": str(int(d.reset_after) + 1),
        }
        if not d.allowed:
            headers["Retry-After"] = str(max(1, int(d.retry_after + 0.999)))
            return JSONResponse(
                {"error": "rate_limit_exceeded",
                 "retry_after": round(d.retry_after, 3)},
                status_code=429,
                headers=headers,
            )
        response = await call_next(request)
        response.headers.update(headers)
        return response
```

`Retry-After` is rounded up and floored at 1 because the header is integer seconds — rounding down invites an immediate retry that fails again.

## Distributed version (required if you run >1 worker)

The in-process limiter multiplies your effective limit by the number of workers. Redis with a Lua script makes the read-modify-write atomic:

```python
import redis

_SCRIPT = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local cost     = tonumber(ARGV[4])

local b = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(b[1]) or capacity
local ts     = tonumber(b[2]) or now

tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
return {allowed, tokens}
"""


class RedisRateLimiter:
    def __init__(self, client: redis.Redis, capacity: float, rate: float) -> None:
        self._script = client.register_script(_SCRIPT)
        self._capacity, self._rate = capacity, rate

    def check(self, key: str, cost: float = 1.0) -> Decision:
        now = time.time()  # wall clock: must be shared across app servers
        allowed, tokens = self._script(
            keys=[f"rl:{key}"], args=[self._capacity, self._rate, now, cost]
        )
        tokens = float(tokens)
        return Decision(
            allowed=bool(allowed),
            limit=int(self._capacity),
            remaining=int(tokens),
            retry_after=0.0 if allowed else (cost - tokens) / self._rate,
            reset_after=(self._capacity - tokens) / self._rate,
        )
```

Caveats worth knowing:
- Time comes from the client, not `redis.call('TIME')`, to keep the script replication-safe. That means your app servers need NTP; clock skew directly skews limits. Alternative: fetch `TIME` once per request and pass it in.
- Fail-open vs fail-closed on Redis outage is a policy decision. Wrap `check` in `try/except redis.RedisError` and pick deliberately — fail-open protects availability, fail-closed protects the backend.
- `EXPIRE` is what keeps the keyspace bounded; the TTL must be ≥ full-refill time or you'd hand out free capacity.

## Why token bucket here

It permits short bursts (good for a browser fetching 10 resources at once) while bounding the sustained rate, and it needs only two numbers per key — unlike a sliding-window log, which stores a timestamp per request. If you need strict smoothing with no bursts at all, use leaky bucket instead (same math, but you drain at a fixed rate rather than allowing an accumulated balance).