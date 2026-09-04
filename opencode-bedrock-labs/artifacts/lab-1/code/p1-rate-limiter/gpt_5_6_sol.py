import math
import threading
import time
from collections import defaultdict
from functools import wraps

from flask import Flask, jsonify, request


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be greater than zero")

        self.capacity = float(capacity)
        self.refill_rate = refill_rate  # Tokens added per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> tuple[bool, float]:
        if tokens <= 0:
            raise ValueError("tokens must be greater than zero")

        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_rate,
            )
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0

            retry_after = (tokens - self.tokens) / self.refill_rate
            return False, retry_after


class RateLimiter:
    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def _get_bucket(self, client_id: str) -> TokenBucket:
        with self.lock:
            bucket = self.buckets.get(client_id)
            if bucket is None:
                bucket = TokenBucket(self.capacity, self.refill_rate)
                self.buckets[client_id] = bucket
            return bucket

    def allow(self, client_id: str, tokens: float = 1.0) -> tuple[bool, float]:
        return self._get_bucket(client_id).consume(tokens)


app = Flask(__name__)

# Allow bursts of 10 requests, replenishing at 2 requests per second.
rate_limiter = RateLimiter(capacity=10, refill_rate=2.0)


def get_client_id() -> str:
    # Only trust X-Forwarded-For when the application is behind a trusted proxy.
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    return request.remote_addr or "unknown"


def rate_limited(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        allowed, retry_after = rate_limiter.allow(get_client_id())

        if not allowed:
            response = jsonify({"error": "rate limit exceeded"})
            response.status_code = 429
            response.headers["Retry-After"] = str(max(1, math.ceil(retry_after)))
            return response

        return function(*args, **kwargs)

    return wrapper


@app.get("/api/resource")
@rate_limited
def resource():
    return jsonify({"message": "Request accepted"})


if __name__ == "__main__":
    app.run()
