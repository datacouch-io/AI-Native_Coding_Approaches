def backoff_schedule(attempts: int, base: float, factor: float,
                      cap: float, max_elapsed: float) -> list[float]:
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise ValueError("attempts must be a non-negative integer")

    for value in (base, factor, cap, max_elapsed):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(
                "base, factor, cap and max_elapsed must be non-negative numbers"
            )

    if attempts == 0:
        return []

    schedule: list[float] = []
    cumulative = 0.0

    for i in range(attempts):
        if cumulative >= max_elapsed:
            break

        delay = base * (factor ** i)
        if delay > cap:
            delay = cap

        remaining = max_elapsed - cumulative
        if delay > remaining:
            delay = remaining
            if delay == 0:
                break

        cumulative += delay
        schedule.append(round(delay, 3))

    return schedule
