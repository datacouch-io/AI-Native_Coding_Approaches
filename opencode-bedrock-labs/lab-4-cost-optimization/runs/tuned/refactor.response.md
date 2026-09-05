I'm in read-only plan mode, so I'll analyze the specification and current implementation to create an optimized refactored version.

Let me examine the current code structure and identify refactoring opportunities:

**Current Implementation Analysis:**

1. **Regex Patterns**: Multiple regex objects are defined at module level, which is good for performance
2. **Constants**: `_UNIT_SECONDS` and `_UNIT_ORDER` are well-organized
3. **parse_duration()**: 
   - Handles non-string input, empty strings, whitespace
   - Detects bare integers correctly
   - Tracks unit ordering and repetition
   - Logic is somewhat verbose with position tracking
4. **format_duration()**: 
   - Correctly handles zero and negative cases
   - Boolean check is good practice
   - Clean divmod loop

**Refactoring Opportunities:**

1. **Consolidate negative number detection**: The separate `_NEGATIVE_BARE_INT_RE` is redundant—the main token regex already matches negative numbers
2. **Improve variable naming**: `pos`, `lowered`, `last_index` could be clearer
3. **Extract unit validation logic**: Reduce duplication between negative checks and unit validation
4. **Simplify bare integer detection**: The current approach with two separate regexes can be unified
5. **Better error messages**: More consistent and informative
6. **Code organization**: Group related logic together more clearly

Here's the refactored implementation:

```python
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

_COMPONENT_RE = re.compile(r"(-?\d+)([dhms])")
_BARE_INTEGER_RE = re.compile(r"^(\d+)$")


def parse_duration(text: str) -> int:
    """Parse a compound duration string into whole seconds.

    Examples: "1h30m", "1h 30m", "2d4h", "90s", "45" (bare seconds).

    Raises DurationError for invalid input (see module contract).
    """
    if not isinstance(text, str):
        raise DurationError(f"duration must be a string, got {type(text).__name__}")

    normalized = text.strip()
    if not normalized:
        raise DurationError("duration string is empty")

    normalized = normalized.lower()

    # Handle bare integer (no unit) as seconds.
    if _BARE_INTEGER_RE.match(normalized):
        return int(normalized)

    # Parse components with units.
    total_seconds = 0
    seen_units = set()
    last_unit_index = -1
    pos = 0

    while pos < len(normalized):
        # Skip whitespace.
        while pos < len(normalized) and normalized[pos] == " ":
            pos += 1
        if pos >= len(normalized):
            break

        match = _COMPONENT_RE.match(normalized, pos)
        if not match:
            raise DurationError(
                f"invalid duration component at position {pos} in {text!r}"
            )

        value_str, unit = match.groups()
        value = int(value_str)

        if value < 0:
            raise DurationError("duration cannot be negative")

        if unit not in _UNIT_SECONDS:
            raise DurationError(f"unknown duration unit: {unit!r}")

        if unit in seen_units:
            raise DurationError(f"repeated duration unit: {unit!r}")

        unit_index = _UNIT_ORDER.index(unit)
        if unit_index <= last_unit_index:
            raise DurationError(
                f"duration units must be in decreasing order (d, h, m, s): "
                f"unexpected {unit!r}"
            )

        seen_units.add(unit)
        last_unit_index = unit_index
        total_seconds += value * _UNIT_SECONDS[unit]
        pos = match.end()

    if not seen_units:
        raise DurationError(f"could not parse any duration components from {text!r}")

    return total_seconds


def format_duration(seconds: int) -> str:
    """Format whole seconds as a compact duration string.

    Examples: 5400 -> "1h30m", 45 -> "45s", 0 -> "0s".

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

    parts = []
    remaining = seconds
    for unit in _UNIT_ORDER:
        unit_value = _UNIT_SECONDS[unit]
        count, remaining = divmod(remaining, unit_value)
        if count:
            parts.append(f"{count}{unit}")

    return "".join(parts)
```