## Accepted duration formats

| Form | Example | Result (seconds) | Notes |
| --- | --- | --- | --- |
| `<n>d` | `"2d"` | `172800` | Days; 1d = 86,400s |
| `<n>h` | `"4h"` | `14400` | Hours; 1h = 3,600s |
| `<n>m` | `"30m"` | `1800` | Minutes; 1m = 60s |
| `<n>s` | `"90s"` | `90` | Seconds; values need not be normalised |
| Bare integer | `"45"` | `45` | Only when the *entire* string is digits |
| Compound | `"1h30m"` | `5400` | Units largest-first, each used at most once |
| Space-separated | `"1h 30m"` | `5400` | Whitespace between components is optional |
| Sparse compound | `"1d 30s"` | `86430` | Intermediate units may be skipped |
| Mixed case | `"1H30M"` | `5400` | Input is lower-cased before parsing |
| Padded | `"  1h30m  "` | `5400` | Leading/trailing whitespace is stripped |

### Rejected input

| Input | Reason |
| --- | --- |
| `""`, `"   "` | Empty or whitespace-only |
| `90` (int), `None` | Not a string |
| `"5w"` | Unknown unit |
| `"1h2h"` | Repeated unit |
| `"30m1h"` | Units out of order (must be largest-first) |
| `"-5m"`, `"+5m"` | Signed values are not allowed |
| `"h"` | Bare unit with no number |
| `"1h30"` | Trailing component with no unit |
| `"1.5h"` | Fractional values are not supported |
