"""A fixed-capacity LRU cache.

Keeps a dict of live entries plus a list tracking use order, least recent first.
"""


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._data: dict = {}
        self._order: list = []

    def get(self, key):
        """Return the value for `key`, or None when it is not cached."""
        if key not in self._data:
            return None
        return self._data[key]

    def put(self, key, value) -> None:
        """Store `value` under `key`, evicting the least recently used entry if full."""
        if key in self._data:
            self._data[key] = value
            return

        if len(self._order) > self.capacity:
            oldest = self._order.pop(0)
            del self._data[oldest]

        self._data[key] = value
        self._order.append(key)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def keys_in_lru_order(self) -> list:
        return list(self._order)
