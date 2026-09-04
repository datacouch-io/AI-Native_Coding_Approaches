## Findings
1. Contract rule 3: `return self._data[key]` in `get` returns without moving a successful lookup to most-recently-used.
2. Contract rule 4: the existing-key branch `self._data[key] = value; return` in `put` updates the value without refreshing recency.
3. Contract rule 5: `if len(self._order) > self.capacity:` checks capacity before insertion with `>` rather than evicting when the new entry would exceed capacity.

```python
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
```