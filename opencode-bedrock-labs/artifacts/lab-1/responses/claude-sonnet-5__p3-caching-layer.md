# Caching Layer Design: Read-Heavy Product Catalog

## Requirements Analysis
- **Read volume**: Millions/day → need low-latency reads, high cache hit ratio
- **Write volume**: Low (a few updates/hour) → staleness window is small and tolerable if bounded
- **Consistency**: Eventual consistency acceptable; strong consistency not required for catalog browsing
- **Access pattern**: Likely power-law/Zipfian — a subset of products (bestsellers, homepage items) get most traffic

## Architecture Decision: Cache-Aside (Lazy Loading)

**Cache-aside over write-through**, because:
- Write-through pays the cache-write cost on every write, but writes are rare here — no benefit
- Write-through risks populating the cache with items that may never be read (cache pollution) — bad for a catalog with a long tail of rarely-viewed SKUs
- Cache-aside naturally caches only what's actually requested, keeping the cache warm with "hot" items
- Failure isolation: if the cache is down, cache-aside degrades gracefully to DB reads; write-through couples write latency to cache availability

Trade-off: cache-aside has a "thundering herd" risk on cold keys and a first-request latency penalty — mitigated below.

## Two-Tier Cache
```
Client → L1: In-process LRU (per app instance, ~ms latency)
       → L2: Distributed cache (Redis/Memcached, shared across instances)
       → L3: Database (source of truth)
```
L1 absorbs the hottest keys without network hops; L2 gives a shared, larger cache that survives instance restarts and avoids redundant DB hits across instances.

## Eviction Policy: LRU with size + TTL bounds
- **LRU** (or LFU-hybrid like Redis's `allkeys-lfu`) fits Zipfian catalog access well — recently/frequently accessed products stay hot, long-tail items get evicted.
- **TTL as a safety net** (e.g., 10–30 min), not the primary invalidation mechanism — bounds worst-case staleness if an explicit invalidation is missed.
- **Max memory / max entries cap** with `maxmemory-policy allkeys-lru` in Redis, or a bounded `Caffeine`/`lru-cache` for L1.

## Invalidation Strategy: Event-driven + TTL fallback
Since updates are infrequent (few/hour) but reads are massive, staleness cost of "wrong info visible for N minutes" must be minimized — so **active invalidation on write**, not just passive TTL expiry:

1. **On catalog update** (admin/service writes to DB):
   - Write to DB (source of truth) first
   - Publish an invalidation event (`product.updated` with product ID) to a pub/sub channel (Redis Pub/Sub, Kafka, SNS)
   - All cache-serving instances subscribe and evict the key from L1 + L2 immediately
2. **TTL fallback** (defense in depth): every cache entry still has a TTL so any missed invalidation self-heals within minutes.
3. **Versioned keys** (optional, avoids race conditions): key = `product:{id}:v{version}`. Bump version on update; old versioned entries just age out via TTL, no explicit delete needed, and eliminates the read-during-invalidation race.

### Handling cache stampede on invalidation/expiry
- **Request coalescing / locking**: only one thread refetches from DB per key; others wait briefly then read from cache.
- **Jittered TTLs**: avoid many keys expiring simultaneously.
- **Stale-while-revalidate**: serve stale data for a short grace period while a background refresh happens, instead of blocking reads.

## Core Cache Logic (Python-style pseudocode)

```python
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
```

## Summary of Key Design Choices

| Concern | Choice | Rationale |
|---|---|---|
| Pattern | Cache-aside | Rare writes, avoids polluting cache with unread items |
| Eviction | LRU/LFU + memory cap | Matches Zipfian catalog access patterns |
| Primary invalidation | Event-driven (pub/sub) on write | Minimizes staleness given low write volume |
| Fallback invalidation | Jittered TTL | Self-heals missed invalidations |
| Stampede protection | Per-key locks + stale-while-revalidate | Prevents DB overload on popular-key expiry |
| Tiering | L1 (process) + L2 (distributed) | Cuts network hops for hottest keys, shares cache across instances |

Since we're in plan mode, no files were created or modified — this is the complete design and implementation as requested. Let me know if you'd like this adapted to a specific stack (e.g., Redis + Spring Cache annotations, or a Node.js/ioredis implementation), or if you'd like to discuss trade-offs like negative caching, cache warming on deploy, or multi-region invalidation.