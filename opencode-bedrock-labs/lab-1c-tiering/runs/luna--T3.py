import math
from numbers import Real


def backoff_schedule(
    attempts: int,
    base: float,
    factor: float,
    cap: float,
    max_elapsed: float,
) -> list[float]:
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < 0
    ):
        raise ValueError("attempts must be a non-negative integer")

    values = (base, factor, cap, max_elapsed)
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        raise ValueError("delay parameters must be non-negative numbers")

    if attempts == 0:
        return []

    schedule: list[float] = []
    elapsed = 0.0
    raw_delay = float(base)

    for _ in range(attempts):
        delay = min(raw_delay, float(cap))
        remaining = float(max_elapsed) - elapsed

        if delay > remaining:
            if remaining == 0:
                break
            delay = remaining

        schedule.append(round(delay, 3))
        elapsed += delay

        if raw_delay == 0 or factor == 0:
            raw_delay = 0.0
        else:
            raw_delay *= float(factor)

    return schedule
