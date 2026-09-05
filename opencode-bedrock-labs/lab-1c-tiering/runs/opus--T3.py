"""Exponential backoff schedule computation."""

from __future__ import annotations

import math


def _check_non_negative_number(value: object, name: str) -> float:
    """Validate that ``value`` is a non-negative, finite real number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative number")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"{name} must be a non-negative number")
    if number < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return number


def backoff_schedule(attempts: int, base: float, factor: float,
                     cap: float, max_elapsed: float) -> list[float]:
    """Return the list of delays to wait before each retry attempt.

    The delay for attempt ``i`` (0-indexed) is ``base * (factor ** i)``, clamped
    to at most ``cap``. The schedule stops early once the cumulative delay would
    exceed ``max_elapsed``; the delay that would breach the budget is truncated
    to exactly the remaining budget, and omitted entirely if that remainder is
    zero. At most ``attempts`` delays are returned, each rounded to 3 decimal
    places.

    Raises:
        ValueError: If ``attempts`` is not a non-negative integer, or if any of
            ``base``, ``factor``, ``cap`` or ``max_elapsed`` is not a
            non-negative number.
    """
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ValueError("attempts must be a non-negative integer")
    if attempts < 0:
        raise ValueError("attempts must be a non-negative integer")

    base_f = _check_non_negative_number(base, "base")
    factor_f = _check_non_negative_number(factor, "factor")
    cap_f = _check_non_negative_number(cap, "cap")
    max_elapsed_f = _check_non_negative_number(max_elapsed, "max_elapsed")

    if attempts == 0:
        return []

    schedule: list[float] = []
    elapsed = 0.0

    for i in range(attempts):
        delay = base_f * (factor_f ** i)
        if delay > cap_f:
            delay = cap_f

        remaining = max_elapsed_f - elapsed
        if remaining <= 0:
            break

        if delay > remaining:
            delay = remaining
            if delay <= 0:
                break
            schedule.append(round(delay, 3))
            elapsed += delay
            break

        schedule.append(round(delay, 3))
        elapsed += delay

    return schedule
