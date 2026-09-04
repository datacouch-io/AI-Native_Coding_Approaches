import time
import threading
from dataclasses import dataclass, field
from functools import wraps
from flask import Flask, request, jsonify


@dataclass
class TokenBucket:
    """
    Token Bucket rate limiter.

    - capacity: maximum number of tokens the bucket can hold (burst limit)
    - refill_rate: tokens added per second (sustained rate)
    """
    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume `tokens`. Returns True if allowed, False if rate-limited."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def time_until_available(self, tokens: int = 1) -> float:
        """Seconds until enough tokens will be available."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                return 0.0
            deficit = tokens - self.tokens
            return deficit / self.refill_rate


class RateLimiter:
    """
    Manages per-client token buckets (e.g., keyed by API key or IP address).
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def _get_bucket(self, key: str) -> TokenBucket:
        with self.lock:
            bucket = self.buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(self.capacity, self.refill_rate)
                self.buckets[key] = bucket
            return bucket

    def allow_request(self, key: str, tokens: int = 1) -> bool:
        return self._get_bucket(key).consume(tokens)

    def retry_after(self, key: str, tokens: int = 1) -> float:
        return self._get_bucket(key).time_until_available(tokens)


# --- Example: Flask middleware/decorator integration ---

app = Flask(__name__)

# Allow 10 requests/sec sustained, burst up to 20 requests
limiter = RateLimiter(capacity=20, refill_rate=10)


def get_client_key() -> str:
    """Identify the client — by API key header, falling back to IP."""
    return request.headers.get("X-API-Key", request.remote_addr)


def rate_limit(tokens: int = 1):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            key = get_client_key()
            if not limiter.allow_request(key, tokens):
                retry_after = limiter.retry_after(key, tokens)
                response = jsonify({
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after_seconds": round(retry_after, 2),
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(int(retry_after) + 1)
                return response
            return f(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/api/resource", methods=["GET"])
@rate_limit(tokens=1)
def get_resource():
    return jsonify({"message": "Here is your resource"})


@app.route("/api/heavy-operation", methods=["POST"])
@rate_limit(tokens=5)  # costs more tokens for expensive endpoints
def heavy_operation():
    return jsonify({"message": "Heavy operation completed"})


if __name__ == "__main__":
    app.run(debug=True)
