"""Parse and format human-written durations.

Supported units are ``d`` (days), ``h`` (hours), ``m`` (minutes) and ``s``
(seconds).  Durations are written as one or more ``<number><unit>`` components
ordered from largest unit to smallest, optionally separated by whitespace::

    "1h30m"     -> 5400
    "1h 30m"    -> 5400
    "2d4h"      -> 187200
    "1d 30s"    -> 86430
    "90s"       -> 90
    "45"        -> 45      (a bare integer means seconds)

Parsing is case-insensitive and surrounding whitespace is ignored.  Anything
else -- an empty string, a non-string, an unknown unit, a repeated or
out-of-order unit, a signed/negative value, a bare unit with no number, or
trailing garbage -- raises :class:`DurationError`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

__all__ = ["DurationError", "parse_duration", "format_duration"]


class DurationError(ValueError):
    """Raised when a duration cannot be parsed or formatted."""


# Largest unit first.  This single table defines both how much each unit is
# worth and the canonical ordering, which is also the only order accepted on
# input, so the two can never fall out of step.
_SECONDS_PER_UNIT: dict[str, int] = {
    "d": 86_400,
    "h": 3_600,
    "m": 60,
    "s": 1,
}
_UNIT_RANK = {unit: rank for rank, unit in enumerate(_SECONDS_PER_UNIT)}

# A bare, unit-less integer is interpreted as a number of seconds.
_BARE_INTEGER_RE = re.compile(r"\d+")
# One component -- digits plus an optional single-letter unit -- followed by any
# whitespace separating it from the next one.  The unit is matched loosely so
# that an unknown unit yields a helpful error instead of a generic mismatch.
_COMPONENT_RE = re.compile(r"(\d+)([a-z]?)\s*")


def parse_duration(text: str) -> int:
    """Return the number of whole seconds described by ``text``.

    Raises:
        DurationError: if ``text`` is not a well-formed duration string.
    """
    if not isinstance(text, str):
        raise DurationError(
            f"duration must be a string, got {type(text).__name__}"
        )

    normalized = text.strip().lower()
    if not normalized:
        raise DurationError("duration must not be empty")

    if normalized[0] in "+-":
        raise DurationError(
            f"invalid duration {text!r}: signed values are not allowed"
        )

    if _BARE_INTEGER_RE.fullmatch(normalized):
        # A bare integer is a count of seconds.
        return int(normalized)

    return sum(
        count * _SECONDS_PER_UNIT[unit]
        for count, unit in _iter_components(normalized, text)
    )


def _iter_components(normalized: str, original: str) -> Iterator[tuple[int, str]]:
    """Yield ``(count, unit)`` pairs for each component of ``normalized``.

    ``normalized`` is the lower-cased, stripped duration; ``original`` is the
    caller's string and is used only in error messages.  The whole input must be
    consumed by well-formed components, each using a known unit that is strictly
    smaller than the one before it.
    """

    def invalid(problem: str) -> DurationError:
        return DurationError(f"invalid duration {original!r}: {problem}")

    seen: set[str] = set()
    previous_unit: str | None = None
    position = 0

    while position < len(normalized):
        match = _COMPONENT_RE.match(normalized, position)
        if match is None:
            raise invalid(f"expected a number at offset {position}")

        digits, unit = match.groups()

        if not unit:
            raise invalid(f"{digits!r} has no unit")
        if unit not in _SECONDS_PER_UNIT:
            raise invalid(f"unknown unit {unit!r}")
        if unit in seen:
            raise invalid(f"repeated unit {unit!r}")
        if previous_unit is not None and _UNIT_RANK[unit] < _UNIT_RANK[previous_unit]:
            raise invalid(
                f"unit {unit!r} must come before {previous_unit!r}"
            )

        seen.add(unit)
        previous_unit = unit
        position = match.end()

        yield int(digits), unit


def format_duration(seconds: int) -> str:
    """Render ``seconds`` as the most compact duration string.

    Zero-valued components are omitted and units appear largest first, so the
    result always round-trips through :func:`parse_duration`.

    Raises:
        DurationError: if ``seconds`` is not a non-negative integer.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise DurationError(
            f"duration must be an integer number of seconds, got "
            f"{type(seconds).__name__}"
        )
    if seconds < 0:
        raise DurationError(f"duration must not be negative, got {seconds}")
    if seconds == 0:
        return "0s"

    parts: list[str] = []
    remaining = seconds
    for unit, unit_seconds in _SECONDS_PER_UNIT.items():
        count, remaining = divmod(remaining, unit_seconds)
        if count:
            parts.append(f"{count}{unit}")
    return "".join(parts)
