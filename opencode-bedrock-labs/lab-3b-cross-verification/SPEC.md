# Specification: `LRUCache`

A fixed-capacity cache that evicts the **least recently used** entry when full.

```python
class LRUCache:
    def __init__(self, capacity: int) -> None: ...
    def get(self, key): ...          # returns the value, or None if absent
    def put(self, key, value) -> None: ...
    def __len__(self) -> int: ...
    @property
    def keys_in_lru_order(self) -> list: ...   # least recent first, most recent last
```

## Contract

1. `capacity` must be a positive integer; anything else raises `ValueError`.
2. `get(key)` returns the stored value, or `None` when the key is absent.
3. **`get` counts as a use.** A successful `get` makes that key the most recently
   used. A miss changes nothing.
4. **`put` counts as a use.** Storing a key - whether new or already present -
   makes it the most recently used. Re-putting an existing key updates its value
   and does not add a second entry.
5. The cache never holds more than `capacity` entries. When a `put` would exceed
   capacity, the least recently used entry is evicted first.
6. `len(cache)` is the number of live entries.
7. `keys_in_lru_order` lists live keys from least to most recently used.
