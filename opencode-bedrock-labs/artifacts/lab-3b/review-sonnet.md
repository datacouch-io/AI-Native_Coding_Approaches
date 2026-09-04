## Findings

1. **Rule 3 violation** — `get()` never updates `self._order` (the method body only reads `self._data`), so a successful `get` does not make the key most-recently-used. This also corrupts the ordering reported by `keys_in_lru_order` (rule 7).
2. **Rule 4 violation** — In `put()`, the early-return branch `if key in self._data: self._data[key] = value; return` updates the value but never moves `key` to the end of `self._order`. Re-putting an existing key does not refresh its recency, again corrupting `keys_in_lru_order` (rule 7).
3. **Rule 5 violation** — The eviction guard `if len(self._order) > self.capacity:` in `put()` uses strict `>` instead of `>=`. Eviction only fires once the cache is already one entry *over* capacity, so a fresh cache permanently ends up holding `capacity + 1` live entries as soon as it fills.

```python
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
```