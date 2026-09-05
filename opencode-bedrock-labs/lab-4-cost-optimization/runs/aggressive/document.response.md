```markdown
# Duration Utilities

`durations.py` provides two small helpers for converting between human-written durations and whole seconds. `parse_duration()` accepts compact or space-separated day, hour, minute, and second components, while `format_duration()` converts a non-negative integer number of seconds into the shortest equivalent duration string. Invalid inputs raise `DurationError`, a subclass of `ValueError`.

## Usage

```python
from durations import DurationError, format_duration, parse_duration

parse_duration("1h30m")     # 5400
parse_duration("2d 4h")     # 187200
parse_duration("45")        # 45; bare integers are seconds
parse_duration("1H 30M")    # 5400; units are case-insensitive

format_duration(5400)       # "1h30m"
format_duration(45)         # "45s"
format_duration(0)          # "0s"
format_duration(187200)     # "2d4h"
```

```python
try:
    parse_duration("1h2h")
except DurationError as error:
    print(error)
```

## Accepted Duration Formats

| Format | Meaning | Example | Result |
| --- | --- | --- | --- |
| Bare integer | Whole seconds | `"45"` | `45` |
| Seconds | Number followed by `s` | `"90s"` | `90` |
| Minutes | Number followed by `m` | `"15m"` | `900` |
| Hours | Number followed by `h` | `"2h"` | `7200` |
| Days | Number followed by `d` | `"1d"` | `86400` |
| Combined components | Adjacent components in largest-to-smallest order | `"1h30m"` | `5400` |
| Space-separated components | Optional whitespace between components | `"2d 4h 15m"` | `188100` |
| Non-contiguous components | Larger units may omit intermediate units | `"1d 30s"` | `86430` |
| Uppercase or mixed-case units | Units are case-insensitive | `"1H30M"` | `5400` |

Units must appear at most once and in this order: `d`, `h`, `m`, `s`. Empty input, negative values, unknown units, bare units, repeated or out-of-order units, and trailing garbage raise `DurationError`.
```