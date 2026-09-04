import time
import random
import threading
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class CacheEntry:
    value: dict
    version: int
    expires_at: float          # absolute epoch seconds
    stale_until: float         # grace period for stale-while-revalidate


class ProductCache:
    """
    Cache-aside layer for product catalog reads.
    L1 = local in-process dict (stand-in for Caffeine/lru-cache)
    L2 = distributed cache client (stand-in for Redis)
    """

    def __init__(self, l2_client, db_client, ttl_seconds=900, stale_grace=60):
        self.l1 = {}                     # local process cache
        self.l2 = l2_client               # e.g. redis client
        self.db = db_client               # source of truth
        self.ttl_seconds = ttl_seconds
        self.stale_grace = stale_grace
        self._locks = {}                  # per-key locks to prevent stampede
        self._locks_guard = threading.Lock()

    def _jittered_ttl(self) -> float:
        # +/-10% jitter to avoid synchronized mass expiry
        jitter = self.ttl_seconds * 0.1
        return time.time() + self.ttl_seconds + random.uniform(-jitter, jitter)

    def _get_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def get_product(self, product_id: str) -> Optional[dict]:
        key = f"product:{product_id}"

        # 1. L1 lookup
        entry = self.l1.get(key)
        now = time.time()

        if entry and now < entry.expires_at:
            return entry.value  # fresh hit, fastest path

        if entry and now < entry.stale_until:
            # Serve stale immediately, refresh in background (non-blocking)
            self._refresh_async(key, product_id)
            return entry.value

        # 2. L2 lookup (miss or fully expired in L1)
        l2_entry = self.l2.get(key)
        if l2_entry and now < l2_entry["expires_at"]:
            self.l1[key] = CacheEntry(
                value=l2_entry["value"],
                version=l2_entry["version"],
                expires_at=l2_entry["expires_at"],
                stale_until=l2_entry["expires_at"] + self.stale_grace,
            )
            return l2_entry["value"]

        # 3. Full miss — load from DB with stampede protection
        return self._load_and_cache(key, product_id)

    def _load_and_cache(self, key: str, product_id: str) -> Optional[dict]:
        lock = self._get_lock(key)
        acquired = lock.acquire(timeout=2)  # bounded wait
        try:
            if acquired:
                # Double-check another thread didn't just populate it
                entry = self.l1.get(key)
                if entry and time.time() < entry.expires_at:
                    return entry.value

                value = self.db.fetch_product(product_id)
                if value is None:
                    return None  # optionally cache negative result briefly

                expires_at = self._jittered_ttl()
                cache_entry = {
                    "value": value,
                    "version": value.get("version", 0),
                    "expires_at": expires_at,
                }
                self.l2.set(key, cache_entry, ttl=self.ttl_seconds + self.stale_grace)
                self.l1[key] = CacheEntry(
                    value=value,
                    version=cache_entry["version"],
                    expires_at=expires_at,
                    stale_until=expires_at + self.stale_grace,
                )
                return value
            else:
                # Couldn't get lock in time — fall back to direct DB read
                # rather than blocking indefinitely
                return self.db.fetch_product(product_id)
        finally:
            if acquired:
                lock.release()

    def _refresh_async(self, key: str, product_id: str):
        threading.Thread(
            target=self._load_and_cache, args=(key, product_id), daemon=True
        ).start()

    def invalidate(self, product_id: str):
        """Called by the write path / event subscriber on catalog update."""
        key = f"product:{product_id}"
        self.l1.pop(key, None)
        self.l2.delete(key)


class CatalogUpdateSubscriber:
    """
    Subscribes to invalidation events published by the write service.
    Ensures all instances evict stale entries immediately after an update,
    instead of waiting for TTL expiry.
    """

    def __init__(self, cache: ProductCache, pubsub_client):
        self.cache = cache
        self.pubsub = pubsub_client

    def start(self):
        for message in self.pubsub.subscribe("product.updated"):
            product_id = message["product_id"]
            self.cache.invalidate(product_id)


# Write path (in the catalog admin/update service)
class CatalogWriteService:
    def __init__(self, db_client, pubsub_client):
        self.db = db_client
        self.pubsub = pubsub_client

    def update_product(self, product_id: str, updates: dict):
        self.db.update_product(product_id, updates)          # 1. write DB
        self.pubsub.publish("product.updated", {"product_id": product_id})  # 2. notify
