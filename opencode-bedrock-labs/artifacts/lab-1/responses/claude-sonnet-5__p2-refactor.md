Here's the refactored version:

```python
def calc(a, b, c, d, calc_type):
    total = a + b + c + d

    if calc_type == "sum":
        return total
    elif calc_type == "avg":
        return total / 4
    else:
        return None
```

Changes made:
- Renamed `type` to `calc_type` to avoid shadowing the built-in `type`.
- Extracted the repeated `a + b + c + d` computation into a single `total` variable.
- Added spacing around operators and after commas for PEP 8 compliance.
- Kept the same control flow and return values, so behavior is unchanged.