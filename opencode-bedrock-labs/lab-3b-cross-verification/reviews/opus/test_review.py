from lru_cache import LRUCache


def test_get_does_not_refresh_recency():
    """Rule 3: a successful get must make the key most recently used."""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.get("a") == 1
    assert cache.keys_in_lru_order == ["b", "a"]


def test_put_existing_key_does_not_refresh_recency():
    """Rule 4: re-putting an existing key must make it most recently used."""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 9)

    assert cache.keys_in_lru_order == ["b", "a"]
    assert len(cache) == 2
    assert cache.get("a") == 9


def test_capacity_exceeded_by_one_entry():
    """Rules 5 and 6: the cache must never hold more than `capacity` entries."""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    assert len(cache) == 2
    assert cache.keys_in_lru_order == ["b", "c"]
    assert cache.get("a") is None


def test_capacity_one_holds_two_entries():
    """Rules 5 and 6: capacity 1 must keep exactly one entry."""
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)

    assert len(cache) == 1
    assert cache.keys_in_lru_order == ["b"]
    assert cache.get("a") is None


def test_eviction_ignores_recency_from_get():
    """Rule 5: the evicted entry must be the least recently used, and get counts."""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.get("a") == 1  # "a" is now most recently used, "b" is the LRU
    cache.put("c", 3)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert len(cache) == 2


def test_eviction_ignores_recency_from_put():
    """Rule 5: a key refreshed by a re-put must not be the eviction victim."""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 1)  # refreshes "a"; "b" becomes the LRU
    cache.put("c", 3)

    assert cache.keys_in_lru_order == ["a", "c"]
