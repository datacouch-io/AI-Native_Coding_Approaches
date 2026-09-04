Here's the refactored version:

```python
from typing import Optional


def calc(a: float, b: float, c: float, d: float, operation: str) -> Optional[float]:
    """Return the sum or average of four values.

    Args:
        a, b, c, d: The values to combine.
        operation: Either "sum" or "avg".

    Returns:
        The sum or the average, or None if the operation is unknown.
    """
    values = (a, b, c, d)

    if operation == "sum":
        return sum(values)
    if operation == "avg":
        return sum(values) / len(values)
    return None
```

What changed and why:

- Renamed the `type` parameter to `operation`; `type` shadows a Python builtin and doesn't describe the value.
- Grouped the four arguments into a `values` tuple so the arithmetic isn't repeated.
- Used `sum()` and `len()` instead of hand-written addition and the hardcoded `4`.
- Dropped the intermediate `x` variable and the `elif`/`else` chain — early returns read more directly.
- Added type hints and a docstring.

Behavior is unchanged: `"sum"` returns the total, `"avg"` returns the total divided by 4 (true division, same as before), and anything else returns `None`. Note `sum()` on ints returns an int just like `a+b+c+d` did.

One thing worth flagging: returning `None` for an unrecognized operation silently hides caller mistakes. Raising `ValueError(f"unknown operation: {operation}")` would be better design, but that changes behavior, so I left it as-is. Let me know if you want that variant.