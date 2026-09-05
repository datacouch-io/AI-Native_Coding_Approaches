def chunk(seq: list, size: int) -> list[list]:
    if not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")
    
    if not seq:
        return []
    
    return [seq[i:i + size] for i in range(0, len(seq), size)]
