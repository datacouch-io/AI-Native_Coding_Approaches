from lru_cache import LRUCache


def test_get_does_not_refresh_recency():
    cache = LRUCache(3)
    cache.put('a', 1)
    cache.put('b', 2)
    cache.put('c', 3)

    cache.get('a')  # a successful get should make 'a' most recently used

    assert cache.keys_in_lru_order == ['b', 'c', 'a']


def test_put_existing_key_does_not_refresh_recency():
    cache = LRUCache(3)
    cache.put('a', 1)
    cache.put('b', 2)
    cache.put('c', 3)

    cache.put('a', 100)  # re-putting an existing key should refresh recency

    assert cache.keys_in_lru_order == ['b', 'c', 'a']
    assert cache.get('a') == 100


def test_capacity_is_exceeded_due_to_off_by_one_eviction_check():
    cache = LRUCache(1)
    cache.put('a', 1)
    cache.put('b', 2)  # capacity is 1, so this must evict 'a'

    assert len(cache) <= 1
    assert cache.keys_in_lru_order == ['b']
