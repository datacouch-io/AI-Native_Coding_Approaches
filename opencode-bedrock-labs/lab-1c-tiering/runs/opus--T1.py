"""Utilities for splitting sequences into fixed-size chunks."""

from __future__ import annotations

__all__ = ["chunk"]


def chunk(seq: list, size: int) -> list[list]:
    """Split ``seq`` into consecutive sublists of length ``size``.

    The final chunk may be shorter than ``size`` and is never padded.

    Args:
        seq: The list to split. It is not mutated.
        size: Positive integer chunk length.

    Returns:
        A list of new lists containing the elements of ``seq`` in order.

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    if isinstance(size, bool) or not isinstance(size, int):
        raise ValueError("size must be a positive integer")
    if size <= 0:
        raise ValueError("size must be a positive integer")

    return [list(seq[i : i + size]) for i in range(0, len(seq), size)]
