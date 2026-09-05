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
