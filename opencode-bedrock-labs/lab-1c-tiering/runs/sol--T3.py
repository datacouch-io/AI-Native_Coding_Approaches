from numbers import Integral, Real


def backoff_schedule(
    attempts: int,
    base: float,
    factor: float,
    cap: float,
    max_elapsed: float,
) -> list[float]:
    if isinstance(attempts, bool) or not isinstance(attempts, Integral) or attempts < 0:
        raise ValueError("attempts must be a non-negative integer")

    values = (base, factor, cap, max_elapsed)
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not value >= 0
        for value in values
    ):
        raise ValueError("base, factor, cap, and max_elapsed must be non-negative numbers")

    schedule: list[float] = []
    elapsed = 0.0

    for attempt in range(attempts):
        try:
            delay = 0.0 if base == 0 else base * (factor ** attempt)
        except OverflowError:
            delay = float("inf")

        delay = min(delay, cap)

        if elapsed + delay > max_elapsed:
            remaining = max_elapsed - elapsed
            if remaining > 0:
                schedule.append(round(float(remaining), 3))
            break

        schedule.append(round(float(delay), 3))
        elapsed += delay

    return schedule
