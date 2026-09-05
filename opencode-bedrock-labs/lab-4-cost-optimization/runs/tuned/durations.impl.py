"""durations.py

Utilities for parsing and formatting human-written, compound duration
strings using the units: d (days), h (hours), m (minutes), s (seconds).
"""

import re

__all__ = ["DurationError", "parse_duration", "format_duration"]


class DurationError(ValueError):
    """Raised when a duration string cannot be parsed or a value cannot
    be formatted."""


_UNIT_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_UNIT_ORDER = "dhms"  # largest to smallest

_BARE_INT_RE = re.compile(r"\d+")
_NEGATIVE_BARE_INT_RE = re.compile(r"-\d+")
_TOKEN_RE = re.compile(r"(-?\d+)([dhms])")


def parse_duration(text: str) -> int:
    """Parse a compound duration string into whole seconds.

    Examples: "1h30m", "1h 30m", "2d4h", "90s", "45" (bare seconds).

    Raises DurationError for invalid input (see module contract).
    """
    if not isinstance(text, str):
        raise DurationError(f"duration must be a string, got {type(text).__name__}")

    stripped = text.strip()
    if not stripped:
        raise DurationError("duration string is empty")

    lowered = stripped.lower()

    # Bare integer (no unit) means seconds.
    if _BARE_INT_RE.fullmatch(lowered):
        return int(lowered)

    if _NEGATIVE_BARE_INT_RE.fullmatch(lowered):
        raise DurationError("duration cannot be negative")

    pos = 0
    length = len(lowered)
    seen_units = set()
    last_index = -1
    total_seconds = 0

    while pos < length:
        # Skip any spaces between components.
        while pos < length and lowered[pos] == " ":
            pos += 1
        if pos >= length:
            break

        match = _TOKEN_RE.match(lowered, pos)
        if not match:
            raise DurationError(
                f"invalid duration component at position {pos} in {text!r}"
            )

        number_str, unit = match.groups()

        if number_str.startswith("-"):
            raise DurationError("duration cannot be negative")

        if unit not in _UNIT_SECONDS:
            raise DurationError(f"unknown duration unit: {unit!r}")

        if unit in seen_units:
            raise DurationError(f"repeated duration unit: {unit!r}")

        unit_index = _UNIT_ORDER.index(unit)
        if unit_index <= last_index:
            raise DurationError(
                f"duration units must be in decreasing order (d, h, m, s): "
                f"unexpected {unit!r}"
            )

        seen_units.add(unit)
        last_index = unit_index
        total_seconds += int(number_str) * _UNIT_SECONDS[unit]
        pos = match.end()

    if not seen_units:
        raise DurationError(f"could not parse any duration components from {text!r}")

    return total_seconds


def format_duration(seconds: int) -> str:
    """Format whole seconds as a compact duration string, e.g. 5400 ->
    "1h30m", 45 -> "45s", 0 -> "0s".

    Raises DurationError for negative or non-integer input.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise DurationError(
            f"seconds must be an integer, got {type(seconds).__name__}"
        )

    if seconds < 0:
        raise DurationError("seconds cannot be negative")

    if seconds == 0:
        return "0s"

    remaining = seconds
    parts = []
    for unit in _UNIT_ORDER:
        unit_seconds = _UNIT_SECONDS[unit]
        value, remaining = divmod(remaining, unit_seconds)
        if value:
            parts.append(f"{value}{unit}")

    return "".join(parts)
