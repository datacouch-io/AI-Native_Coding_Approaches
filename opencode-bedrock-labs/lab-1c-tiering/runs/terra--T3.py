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
        or value < 0
        for value in values
    ):
        raise ValueError(
            "base, factor, cap, and max_elapsed must be non-negative numbers"
        )

    schedule = []
    elapsed = 0.0

    for attempt in range(attempts):
        delay = min(base * (factor ** attempt), cap)
        remaining = max_elapsed - elapsed

        if remaining <= 0:
            break

        if delay > remaining:
            schedule.append(round(remaining, 3))
            break

        schedule.append(round(delay, 3))
        elapsed += delay

    return schedule
