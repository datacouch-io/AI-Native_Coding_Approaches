"""Correct reference implementation - used to validate reviewer findings.

A reviewer's reproducing test must FAIL against the flawed module and PASS
against this one. A test that fails against both is a bad test, not a finding.
"""


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._data: dict = {}
        self._order: list = []

    def _touch(self, key) -> None:
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def get(self, key):
        if key not in self._data:
            return None
        self._touch(key)
        return self._data[key]

    def put(self, key, value) -> None:
        if key in self._data:
            self._data[key] = value
            self._touch(key)
            return

        if len(self._order) >= self.capacity:
            oldest = self._order.pop(0)
            del self._data[oldest]

        self._data[key] = value
        self._order.append(key)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def keys_in_lru_order(self) -> list:
        return list(self._order)
