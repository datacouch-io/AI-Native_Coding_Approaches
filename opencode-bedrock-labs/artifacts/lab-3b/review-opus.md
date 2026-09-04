All defect claims below were executed against both the code under review and a reference implementation (each test fails on the reviewed code, passes on a correct one).

## Findings

1. **Rule 3 violated** — `get` never records a use. In `get`, the hit path is just `return self._data[key]`; `self._order` is never touched, so a successful `get` does not make the key most recently used. Proven by `test_get_does_not_refresh_recency`.
2. **Rule 4 violated** — `put` on an existing key does not record a use. The branch `if key in self._data: self._data[key] = value; return` updates the value and returns early without moving `key` to the end of `self._order`. (The value update itself and the no-duplicate-entry part of rule 4 are correct.) Proven by `test_put_existing_key_does_not_refresh_recency`.
3. **Rules 5 and 6 violated (off-by-one)** — the eviction guard `if len(self._order) > self.capacity:` should trigger at `>=`. As written, the cache grows to `capacity + 1` live entries before it ever evicts, so `len(cache)` exceeds `capacity`. Proven by `test_capacity_exceeded_by_one_entry` and `test_capacity_one_holds_two_entries`.
4. **Rule 5 violated (wrong victim)** — because `self._order` records insertion order only (defects 1 and 2), `self._order.pop(0)` evicts the oldest *inserted* entry, not the least recently *used* one; a key refreshed by `get` or by a re-`put` is still evicted first. Proven by `test_eviction_ignores_recency_from_get` and `test_eviction_ignores_recency_from_put`.

No defect found for rule 1 (`capacity` validation correctly rejects non-ints, `bool`, and values `<= 0`), rule 2 (miss returns `None`, and a miss mutates nothing), or the copy-on-read behaviour of `keys_in_lru_order`.

```python
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
```