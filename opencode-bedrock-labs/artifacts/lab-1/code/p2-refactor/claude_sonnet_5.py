def calc(a, b, c, d, calc_type):
    total = a + b + c + d

    if calc_type == "sum":
        return total
    elif calc_type == "avg":
        return total / 4
    else:
        return None
