from lru_cache import LRUCache


def test_get_does_not_refresh_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.get("a") == 1
    assert cache.keys_in_lru_order == ["b", "a"]


def test_reput_existing_key_does_not_refresh_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    cache.put("a", 3)

    assert cache.keys_in_lru_order == ["b", "a"]


def test_put_allows_cache_to_exceed_capacity():
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)

    assert len(cache) == 1
    assert cache.keys_in_lru_order == ["b"]
    assert cache.get("a") is None
    assert cache.get("b") == 2
