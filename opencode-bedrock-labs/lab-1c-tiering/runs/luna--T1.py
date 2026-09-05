def chunk(seq: list, size: int) -> list[list]:
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")

    return [seq[index:index + size] for index in range(0, len(seq), size)]
