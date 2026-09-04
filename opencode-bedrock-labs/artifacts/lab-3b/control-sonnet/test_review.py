from lru_cache import LRUCache


def test_init_accepts_bool_true_as_valid_positive_integer_capacity():
    # Rule 1: "capacity must be a positive integer; anything else raises
    # ValueError." `True` IS an instance of `int` with value 1 (a positive
    # integer per Python's own type system: isinstance(True, int) is True),
    # so it must be accepted, not rejected. The implementation's explicit
    # `isinstance(capacity, bool)` check wrongly raises ValueError for it.
    cache = LRUCache(True)
    assert cache.capacity == 1
    assert len(cache) == 0
