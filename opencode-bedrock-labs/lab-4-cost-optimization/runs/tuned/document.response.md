```markdown
# Duration Utilities

`durations.py` provides lightweight helpers for converting human-written duration strings to whole seconds and formatting non-negative whole-second values into compact duration strings. Supported units are days (`d`), hours (`h`), minutes (`m`), and seconds (`s`); parsing is case-insensitive, accepts optional spaces between components, and treats a standalone integer as seconds.

## Usage

```python
from durations import DurationError, format_duration, parse_duration

parse_duration("1h30m")    # 5400
parse_duration("2d 4h")    # 187200
parse_duration("45")       # 45
parse_duration("1H 30M")   # 5400

format_duration(5400)      # "1h30m"
format_duration(45)        # "45s"
format_duration(0)         # "0s"
format_duration(90061)     # "1d1h1m1s"
```

Invalid input raises `DurationError`:

```python
parse_duration("1h2h")     # repeated unit
parse_duration("1h30")     # trailing bare number
parse_duration("-5m")      # negative value
format_duration(-1)        # negative value
```

## Accepted Duration Formats

| Format | Meaning | Example | Result |
| --- | --- | --- | --- |
| Bare integer | Seconds | `"45"` | `45` |
| Single component | A number followed by `d`, `h`, `m`, or `s` | `"90s"` | `90` |
| Adjacent components | Largest-to-smallest unit components without spaces | `"1h30m"` | `5400` |
| Space-separated components | Components separated by optional spaces | `"1h 30m"` | `5400` |
| Non-contiguous components | Larger-to-smaller units with omitted units allowed | `"1d 30s"` | `86430` |
| Case-insensitive units | Uppercase and lowercase units are equivalent | `"2D4H"` | `187200` |
| Surrounding whitespace | Leading and trailing whitespace is ignored | `"  5m  "` | `300` |
```