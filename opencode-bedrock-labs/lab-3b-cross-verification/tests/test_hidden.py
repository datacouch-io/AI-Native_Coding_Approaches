"""Ground truth for the planted defects. Never shown to any model.

Used only to answer: did the reviewer's findings correspond to real defects,
and did the revision actually fix them?
"""
import pytest

from lru_cache import LRUCache


class TestContractBasics:
    """Behaviour the flawed starter already gets right - it must not look broken."""

    def test_rejects_non_positive_capacity(self):
        for bad in (0, -1, 1.5, "3", True):
            with pytest.raises(ValueError):
                LRUCache(bad)

    def test_get_miss_returns_none(self):
        assert LRUCache(2).get("nope") is None

    def test_put_then_get_roundtrip(self):
        c = LRUCache(2)
        c.put("a", 1)
        assert c.get("a") == 1

    def test_reput_updates_value_without_duplicating(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("a", 2)
        assert c.get("a") == 2
        assert len(c) == 1


class TestDefectA_GetDoesNotRefreshRecency:
    def test_recent_get_protects_key_from_eviction(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        assert c.get("a") == 1          # 'a' is now the most recently used
        c.put("c", 3)                   # must evict 'b', the least recently used
        assert c.get("a") == 1, "a was used most recently and must survive"
        assert c.get("b") is None, "b was least recently used and must be evicted"

    def test_get_moves_key_to_most_recent_position(self):
        c = LRUCache(3)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        c.get("a")
        assert c.keys_in_lru_order == ["b", "c", "a"]


class TestDefectB_CapacityOffByOne:
    def test_never_exceeds_capacity(self):
        c = LRUCache(2)
        for i, k in enumerate("abcd"):
            c.put(k, i)
            assert len(c) <= 2, f"cache grew to {len(c)} with capacity 2"

    def test_third_insert_evicts_first(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        assert len(c) == 2
        assert c.get("a") is None, "a should have been evicted at capacity"


class TestDefectC_ReputDoesNotRefreshRecency:
    def test_reput_makes_key_most_recent(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 99)                  # 'a' is used again, so 'b' is now LRU
        c.put("c", 3)                   # must evict 'b'
        assert c.get("a") == 99, "a was re-put and must survive"
        assert c.get("b") is None, "b was least recently used and must be evicted"
