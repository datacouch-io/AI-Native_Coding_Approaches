```python
"""durations.py

Utility functions for parsing and formatting human-written durations.

Supported units:
    d - days
    h - hours
    m - minutes
    s - seconds

See module docstring examples in ``parse_duration`` and ``format_duration``
for the exact contract this module implements.
"""

from __future__ import annotations

import re

__all__ = ["DurationError", "parse_duration", "format_duration"]


class DurationError(ValueError):
    """Raised when a duration string or seconds value is invalid."""


# Unit metadata: letter -> (seconds multiplier, rank for ordering)
# Rank order enforces "largest to smallest" (d < h < m < s).
_UNIT_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_UNIT_RANK = {"d": 0, "h": 1, "m": 2, "s": 3}

# A single component: one or more digits followed by a unit letter.
_COMPONENT_RE = re.compile(r"(\d+)([dhms])")
# The entire (whitespace-stripped) string must be made up of components.
_FULL_RE = re.compile(r"(?:\d+[dhms])+")


def parse_duration(text: str) -> int:
    """Parse a compound duration string into whole seconds.

    Examples:
        "1h30m"  -> 5400
        "1h 30m" -> 5400
        "2d4h"   -> 187200
        "90s"    -> 90
        "45"     -> 45
        "1H30M"  -> 5400

    Raises:
        DurationError: on empty/whitespace-only input, non-string input,
            unknown units, repeated units, out-of-order units, negative
            values, bare units with no number, or trailing garbage.
    """
    if not isinstance(text, str):
        raise DurationError(f"duration must be a string, got {type(text).__name__}")

    stripped = text.strip()
    if not stripped:
        raise DurationError("duration string is empty")

    # Remove internal whitespace too; spaces are purely optional separators
    # between components (e.g. "1h 30m" == "1h30m").
    normalized = "".join(stripped.split()).lower()

    # Bare integer with no unit means seconds.
    if normalized.isdigit():
        return int(normalized)

    if not _FULL_RE.fullmatch(normalized):
        raise DurationError(f"invalid duration string: {text!r}")

    seen_ranks: list[int] = []
    total = 0
    for match in _COMPONENT_RE.finditer(normalized):
        value_str, unit = match.group(1), match.group(2)
        rank = _UNIT_RANK[unit]

        if seen_ranks and rank <= seen_ranks[-1]:
            if rank == seen_ranks[-1]:
                raise DurationError(f"repeated unit {unit!r} in duration: {text!r}")
            raise DurationError(
                f"units out of order in duration: {text!r} "
                "(expected largest-to-smallest: d, h, m, s)"
            )
        seen_ranks.append(rank)

        total += int(value_str) * _UNIT_SECONDS[unit]

    return total


def format_duration(seconds: int) -> str:
    """Render whole seconds into the most compact duration string.

    Examples:
        5400  -> "1h30m"
        45    -> "45s"
        0     -> "0s"
        86400 -> "1d"

    Raises:
        DurationError: if ``seconds`` is not a non-negative integer.
    """
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise DurationError(f"seconds must be an int, got {type(seconds).__name__}")
    if seconds < 0:
        raise DurationError("seconds must be non-negative")

    remainder = seconds
    days, remainder = divmod(remainder, _UNIT_SECONDS["d"])
    hours, remainder = divmod(remainder, _UNIT_SECONDS["h"])
    minutes, secs = divmod(remainder, _UNIT_SECONDS["m"])

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")

    return "".join(parts)
```