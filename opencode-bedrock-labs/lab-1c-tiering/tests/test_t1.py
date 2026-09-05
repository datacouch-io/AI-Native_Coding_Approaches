"""T1 acceptance - hidden from every model."""
import pytest
from solution import chunk


def test_even_split():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

def test_ragged_final_chunk_not_padded():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

def test_size_larger_than_seq():
    assert chunk([1, 2], 5) == [[1, 2]]

def test_empty_returns_empty():
    assert chunk([], 3) == []

def test_size_one():
    assert chunk([1, 2, 3], 1) == [[1], [2], [3]]

@pytest.mark.parametrize("bad", [0, -1, 1.5, "2", None])
def test_invalid_size_raises(bad):
    with pytest.raises(ValueError):
        chunk([1, 2, 3], bad)

def test_input_not_mutated():
    original = [1, 2, 3, 4, 5]
    copy = list(original)
    chunk(original, 2)
    assert original == copy

def test_returns_new_lists():
    original = [1, 2, 3, 4]
    out = chunk(original, 2)
    out[0].append(99)
    assert original == [1, 2, 3, 4]
