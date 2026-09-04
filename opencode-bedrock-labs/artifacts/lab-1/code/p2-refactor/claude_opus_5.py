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
