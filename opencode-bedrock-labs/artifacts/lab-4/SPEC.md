# Specification: `durations.py`

A small utility for parsing and formatting human-written durations.

```python
class DurationError(ValueError): ...

def parse_duration(text: str) -> int: ...
def format_duration(seconds: int) -> str: ...
```

## Contract

1. `parse_duration` accepts a compound duration string and returns whole seconds.
   Units: `d` (days), `h` (hours), `m` (minutes), `s` (seconds).
2. Components may be combined and separated by optional spaces: `"1h30m"`,
   `"1h 30m"`, `"2d4h"`, `"90s"`. Order is largest-to-smallest but need not be
   contiguous (`"1d 30s"` is valid).
3. A bare integer with no unit means seconds: `"45"` -> 45.
4. Parsing is case-insensitive: `"1H30M"` == `"1h30m"`.
5. Leading and trailing whitespace is ignored.
6. These raise `DurationError`: empty or whitespace-only input, a non-string
   input, an unknown unit (`"5w"`), a repeated unit (`"1h2h"`), a negative value
   (`"-5m"`), a bare unit with no number (`"h"`), and any trailing garbage
   (`"1h30"` is invalid because `30` has no unit and is not the whole string).
7. `format_duration` renders whole seconds back to the most compact form using
   the same units, largest first, omitting zero components: `5400` -> `"1h30m"`,
   `45` -> `"45s"`, `0` -> `"0s"`, `86400` -> `"1d"`.
8. `format_duration` raises `DurationError` for a negative or non-integer input.
9. Round-trip: for any non-negative integer `n`, `parse_duration(format_duration(n)) == n`.
