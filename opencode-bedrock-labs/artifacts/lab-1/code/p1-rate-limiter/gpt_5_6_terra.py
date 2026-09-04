from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.

    rate: Tokens replenished per second.
    capacity: Maximum burst size.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than zero")
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")

        self.rate = rate
        self.capacity = capacity
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        """Return True and consume tokens if this request is allowed."""
        if cost <= 0:
            raise ValueError("cost must be greater than zero")
        if cost > self.capacity:
            return False

        now = time.monotonic()

        with self._lock:
            bucket = self._buckets.get(key)

            if bucket is None:
                bucket = _Bucket(tokens=float(self.capacity), last_refill=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.last_refill
                bucket.tokens = min(
                    float(self.capacity),
                    bucket.tokens + elapsed * self.rate,
                )
                bucket.last_refill = now

            if bucket.tokens < cost:
                return False

            bucket.tokens -= cost
            return True

    def retry_after(self, key: str, cost: int = 1) -> float:
        """Return seconds until a request costing `cost` tokens is allowed."""
        if cost <= 0:
            raise ValueError("cost must be greater than zero")
        if cost > self.capacity:
            return float("inf")

        now = time.monotonic()

        with self._lock:
            bucket = self._buckets.get(key)

            if bucket is None:
                return 0.0

            elapsed = now - bucket.last_refill
            available = min(
                float(self.capacity),
                bucket.tokens + elapsed * self.rate,
            )
            return max(0.0, (cost - available) / self.rate)


# Example framework-agnostic usage:
#
# limiter = TokenBucketRateLimiter(rate=10, capacity=20)
#
# def handle_request(client_ip: str):
#     if not limiter.allow(client_ip):
#         retry_after = limiter.retry_after(client_ip)
#         return {
#             "status": 429,
#             "headers": {"Retry-After": str(max(1, int(retry_after + 0.999)))},
#             "body": {"error": "Too many requests"},
#         }
#
#     return {"status": 200, "body": {"message": "OK"}}
