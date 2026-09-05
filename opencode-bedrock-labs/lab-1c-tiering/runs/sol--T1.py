def chunk(seq: list, size: int) -> list[list]:
    if type(size) is not int or size <= 0:
        raise ValueError("size must be a positive integer")
    return [seq[index:index + size] for index in range(0, len(seq), size)]
