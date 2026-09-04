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
