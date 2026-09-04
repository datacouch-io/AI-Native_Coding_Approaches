```python
def calc(a, b, c, d, calculation_type):
    total = a + b + c + d

    if calculation_type == "sum":
        return total
    if calculation_type == "avg":
        return total / 4

    return None
```