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
