"""Reference solution - proves the acceptance suite is satisfiable. Not shipped to models."""
import re

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_ORDER = ["d", "h", "m", "s"]
_TOKEN = re.compile(r"(\d+)([dhms])")


class DurationError(ValueError):
    pass


def parse_duration(text: str) -> int:
    if not isinstance(text, str):
        raise DurationError(f"expected a string, got {type(text).__name__}")
    cleaned = text.strip().lower().replace(" ", "")
    if not cleaned:
        raise DurationError("empty duration")
    if cleaned.isdigit():
        return int(cleaned)

    total, seen, pos = 0, set(), 0
    for match in _TOKEN.finditer(cleaned):
        if match.start() != pos:
            raise DurationError(f"unparseable duration: {text!r}")
        value, unit = match.groups()
        if unit in seen:
            raise DurationError(f"repeated unit {unit!r} in {text!r}")
        seen.add(unit)
        total += int(value) * _UNITS[unit]
        pos = match.end()
    if pos != len(cleaned) or not seen:
        raise DurationError(f"unparseable duration: {text!r}")
    return total


def format_duration(seconds: int) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise DurationError(f"expected an int, got {type(seconds).__name__}")
    if seconds < 0:
        raise DurationError("duration must not be negative")
    if seconds == 0:
        return "0s"
    parts, remaining = [], seconds
    for unit in _ORDER:
        size = _UNITS[unit]
        count, remaining = divmod(remaining, size)
        if count:
            parts.append(f"{count}{unit}")
    return "".join(parts)
