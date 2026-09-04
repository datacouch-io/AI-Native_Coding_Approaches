def calc(a, b, c, d, type):
    total = a + b + c + d

    if type == "sum":
        return total
    if type == "avg":
        return total / 4

    return None
