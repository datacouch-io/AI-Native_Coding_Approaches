This repo is a benchmark harness (`run_benchmark.py` + `prompts/p3-caching-layer.txt`), so here is the answer inline — no files touched.

---

# Caching layer: read-heavy product catalog

## 1. Workload characterization (drives every decision)

| Property | Value | Implication |
|---|---|---|
| Reads | ~10^6–10^7/day, bursty (avg ~50 rps, peak 10–20x) | Cache must absorb ~95%+ of traffic |
| Writes | a few/hour, from CMS/ETL, often **batched** | Invalidation cost is irrelevant; batch churn is the real risk |
| Read:write ratio | ~10^5:1 | Aggressive caching, long TTLs |
| Access distribution | Zipfian (hot SKUs, long cold tail); periodic crawler/bulk scans | Favors **LFU** over LRU |
| Staleness tolerance | Descriptions/media: minutes OK. Price/availability: seconds. | Event-driven invalidation with TTL as safety net |
| Corpus size | e.g. 5M SKUs × ~4KB × locales ≫ RAM | Cannot cache everything → **cache-aside**, not warm-everything |

Explicit SLO to design against: **99% of catalog updates visible within 2s; hard bound 5s (L1) / 1h (L2).** Without a stated staleness SLO the rest is unfalsifiable.

## 2. Topology: two tiers

```
client → app instance
           ├─ L1: in-process TTL-LRU (~10k entries, 5s TTL)   → ~0.01ms, kills hot-key fanout
           ├─ L2: Redis cluster (shared, 1h TTL, allkeys-lfu)  → ~1ms
           └─ origin: Postgres/read replica (concurrency-limited)
```

L1 exists because a Zipfian head means a handful of SKUs generate a large share of requests; serving those from process memory removes both Redis CPU and network p99 tail. Its 5s TTL bounds worst-case staleness even if the invalidation broadcast is lost.

## 3. Eviction policy

- **L2 (Redis): `maxmemory-policy allkeys-lfu`.** Catalog access is strongly skewed and periodically scanned by crawlers/bulk sync jobs. Under LRU a single full-catalog scan evicts the entire hot set (cache pollution); LFU's frequency counters keep the head resident. Provision for the hot 5–10% (~2–4GB), not the full corpus.
- **L1 (in-process): TTL + LRU, small and bounded by entry count.** At 10k entries recency ≈ frequency, and LRU is O(1) with no counter decay tuning.
- **TTL jitter (±10%)** on every write so bulk-loaded keys don't expire in lockstep.
- Deliberately **not** `volatile-*`: every key gets a TTL, so `allkeys-*` and `volatile-*` are equivalent except that `allkeys` fails safe if a TTL is ever forgotten.

## 4. Cache-aside vs write-through

**Cache-aside (read-through helper) for the general path. Write-through only for a hot-key allowlist.**

Reasoning:

- The write path is not the service — updates arrive from a CMS/ETL pipeline out-of-band. Write-through would couple that pipeline's availability and latency to Redis, and require every writer to know the cache's serialization format and key layout.
- Write-through populates keys that may never be read. With millions of cold SKUs that wastes the memory that should hold the hot set, and actively hurts under LFU (new keys enter with low frequency and thrash).
- Cache-aside degrades gracefully: cache down ⇒ slow, not broken. Write-behind additionally risks data loss and is unjustifiable here — the DB is the system of record and write volume is trivial.

The one exception: after a *bulk* price update, thousands of hot keys get invalidated simultaneously and the resulting fill burst is the single most likely outage cause. For the tracked top-N SKUs, the invalidation consumer **proactively refills** (write-through-ish) instead of leaving a hole.

## 5. Invalidation strategy

Layered, primary mechanism first, each lower layer bounding the failure of the one above:

1. **Event-driven delete (primary).** Catalog writes emit a change event via transactional outbox / CDC (Debezium → Kafka/SNS). A consumer deletes the L2 key and publishes to a Redis pub/sub channel; every app instance drops it from L1. Typical write→visible lag: 100ms–1s.
2. **Delete, never update-in-place.** An `UPDATE` from the event stream races with concurrent cache-aside fills and with out-of-order events; a delete is idempotent and order-insensitive.
3. **Version-guarded fills + write lease (fixes the classic cache-aside race).** The race: reader misses, loads v1 from DB, writer commits v2 and deletes the key, reader then writes v1 → stale entry persists for a full TTL. Two guards, both in the Lua below: (a) every entry carries the row's monotonic `version`, and a fill is rejected if it would lower the stored version; (b) invalidation sets a short-lived **tombstone lease** (~1s, > p99 DB fill latency) that suppresses *any* fill for that key. Cheaper and more correct than "delayed double delete".
4. **Key epoch for mass changes.** Keys are prefixed `cat:v{epoch}:…`. A full re-index or schema change bumps the epoch in config → instant logical flush, no `SCAN`+`DEL` storm, and the old generation ages out via TTL. (Never `FLUSHDB` in production.)
5. **TTL as the backstop, not the mechanism.** 1h in L2, 5s in L1. Its only job is bounding staleness when an event is dropped. Tighten to ~60s for the price/inventory namespace, which has the strictest tolerance.

Separate the namespaces: `product:{id}` entities (long TTL) vs `list:{query-hash}` → array of IDs (60–120s TTL). Listings/search results are a combinatorial explosion of filters and rankings; caching IDs only and hydrating via `MGET` keeps entity cache hit ratio high and makes invalidation tractable.

## 6. Stampede, failure, and correctness protections

- **Singleflight** per process (dedupes concurrent misses for the same key) + **distributed lock** `SET NX PX` (dedupes across instances) → one DB query per key per miss, regardless of concurrency.
- **Stale-while-revalidate**: entries have a soft expiry; past it, serve stale immediately and refresh in the background. Under origin failure, serve stale up to a grace window rather than 500.
- **Negative caching** for not-found (30s, short) to stop enumeration/crawler traffic from hammering the DB. Distinct from "miss" so it can't be confused with an empty cache.
- **Fail-open with a bulkhead.** Redis calls get a hard 20ms timeout; a timeout is treated as a miss. But a cache-wide outage turning 100% of traffic into DB queries is how you convert a cache incident into a database incident — so origin loads pass through a semaphore (bounded concurrency) plus a circuit breaker that sheds load / serves stale.
- **Batch reads** via pipelined `MGET`, never N round-trips.
- **Compact payloads**: msgpack/protobuf, not JSON, and compress >1KB blobs. Directly buys hot-set capacity.

Metrics that matter: hit ratio per tier, **invalidation lag (commit→visible)** as a histogram, stale-serve rate, origin load shed count, Redis evictions/s and memory, p99 fill latency. Alert on hit ratio drop and invalidation lag, not on cache CPU.

## 7. Core cache logic

```python
"""Two-tier (in-process LRU + Redis) cache-aside layer for a read-heavy catalog."""
from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Iterable, Sequence, TypeVar

import msgpack  # compact wire format; JSON wastes hot-set memory
from redis.asyncio import Redis

T = TypeVar("T")

MISSING = object()          # cache miss
NEGATIVE = object()         # cached "does not exist"

# ---------------------------------------------------------------------------
# Atomic server-side primitives.
# ---------------------------------------------------------------------------

# Fill is rejected if (a) a newer version is already cached, or (b) an
# invalidation lease is active. Together these close the cache-aside
# stale-fill race without any coordination on the read path.
_LUA_FILL = """
local lease = redis.call('EXISTS', KEYS[2])
if lease == 1 then return 0 end
local cur = redis.call('HGET', KEYS[1], 'v')
if cur and tonumber(cur) >= tonumber(ARGV[1]) then return 0 end
redis.call('HSET', KEYS[1], 'v', ARGV[1], 'd', ARGV[2], 't', ARGV[3])
redis.call('PEXPIRE', KEYS[1], ARGV[4])
return 1
"""

# Delete + tombstone lease. The lease must outlive the slowest in-flight
# origin read (set it to ~p99.9 fill latency) so no reader can resurrect
# a pre-write value.
_LUA_INVALIDATE = """
redis.call('DEL', KEYS[1])
redis.call('SET', KEYS[2], '1', 'PX', ARGV[1])
return 1
"""


@dataclass(slots=True)
class Entry(Generic[T]):
    value: T | None      # None == negative (row does not exist)
    version: int         # monotonic row version; guards out-of-order fills
    stored_at: float
    soft_ttl: float

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self.stored_at) > self.soft_ttl


class TTLLRU:
    """L1: bounded, TTL'd, O(1). Sized by entry count, evicted by recency."""

    def __init__(self, capacity: int, ttl: float) -> None:
        self._cap, self._ttl = capacity, ttl
        self._data: OrderedDict[str, tuple[float, Entry]] = OrderedDict()

    def get(self, key: str) -> Entry | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        expires_at, entry = hit
        if time.monotonic() >= expires_at:      # TTL bounds staleness even if
            del self._data[key]                 # the invalidation broadcast is lost
            return None
        self._data.move_to_end(key)
        return entry

    def put(self, key: str, entry: Entry) -> None:
        self._data[key] = (time.monotonic() + self._ttl, entry)
        self._data.move_to_end(key)
        while len(self._data) > self._cap:
            self._data.popitem(last=False)      # LRU eviction

    def drop(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


class CatalogCache:
    """
    Cache-aside with singleflight, stale-while-revalidate, negative caching,
    version-guarded fills, and fail-open origin bulkheading.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        epoch: int = 1,                     # bump for mass invalidation
        hard_ttl: float = 3600.0,           # L2 backstop, not the mechanism
        soft_ttl: float = 300.0,            # revalidate-after
        negative_ttl: float = 30.0,
        l1_capacity: int = 10_000,
        l1_ttl: float = 5.0,                # worst-case L1 staleness
        lease_ms: int = 1_000,              # > p99.9 origin fill latency
        redis_timeout: float = 0.02,        # a slow cache must never be the SLO
        max_origin_concurrency: int = 32,   # bulkhead: cache outage != DB outage
    ) -> None:
        self._r = redis
        self._epoch = epoch
        self._hard_ttl, self._soft_ttl = hard_ttl, soft_ttl
        self._negative_ttl = negative_ttl
        self._lease_ms = lease_ms
        self._timeout = redis_timeout
        self._l1 = TTLLRU(l1_capacity, l1_ttl)
        self._inflight: dict[str, asyncio.Future] = {}   # singleflight
        self._origin_gate = asyncio.Semaphore(max_origin_concurrency)
        self._fill = redis.register_script(_LUA_FILL)
        self._invalidate_script = redis.register_script(_LUA_INVALIDATE)
        self._bg: set[asyncio.Task] = set()

    # -- key layout: epoch prefix makes bulk invalidation O(1) --------------
    def _k(self, kind: str, ident: str) -> str:
        return f"cat:v{self._epoch}:{kind}:{ident}"

    @staticmethod
    def _lease(key: str) -> str:
        return f"{key}:lease"

    # -- read path ---------------------------------------------------------
    async def get(
        self,
        kind: str,
        ident: str,
        loader: Callable[[], Awaitable[tuple[T | None, int]]],
    ) -> T | None:
        """`loader()` returns (value_or_None, monotonic_row_version)."""
        key = self._k(kind, ident)

        if (entry := self._l1.get(key)) is not None:
            if entry.is_stale:
                self._spawn(self._refresh(key, loader))   # stale-while-revalidate
            return entry.value

        entry = await self._l2_get(key)
        if entry is not None:
            self._l1.put(key, entry)
            if entry.is_stale:
                self._spawn(self._refresh(key, loader))
            return entry.value

        return await self._singleflight(key, loader)

    async def get_many(
        self,
        kind: str,
        idents: Sequence[str],
        batch_loader: Callable[[Sequence[str]], Awaitable[dict[str, tuple[T, int]]]],
    ) -> dict[str, T | None]:
        """Pipelined MGET-equivalent; one origin query for all misses."""
        keys = {i: self._k(kind, i) for i in idents}
        out: dict[str, T | None] = {}
        pending: list[str] = []

        for ident, key in keys.items():
            if (entry := self._l1.get(key)) is not None:
                out[ident] = entry.value
            else:
                pending.append(ident)

        if pending:
            pipe = self._r.pipeline(transaction=False)
            for ident in pending:
                pipe.hgetall(keys[ident])
            raws = await self._guard(pipe.execute(), default=[None] * len(pending))
            still_missing: list[str] = []
            for ident, raw in zip(pending, raws or []):
                entry = self._decode(raw)
                if entry is None:
                    still_missing.append(ident)
                else:
                    self._l1.put(keys[ident], entry)
                    out[ident] = entry.value
            pending = still_missing

        if pending:
            async with self._origin_gate:
                loaded = await batch_loader(pending)
            for ident in pending:
                value, version = loaded.get(ident, (None, 0))
                out[ident] = value
                self._spawn(self._store(keys[ident], value, version))
        return out

    # -- write path: delete + lease, then broadcast to every L1 ------------
    async def invalidate(self, kind: str, ident: str) -> None:
        key = self._k(kind, ident)
        await self._guard(
            self._invalidate_script(keys=[key, self._lease(key)], args=[self._lease_ms])
        )
        self._l1.drop(key)
        await self._guard(self._r.publish("cat:inval", key))

    async def subscribe_invalidations(self) -> None:
        """Run per process: applies peer invalidations to L1."""
        pubsub = self._r.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe("cat:inval")
        async for msg in pubsub.listen():
            payload = msg["data"]
            key = payload.decode() if isinstance(payload, bytes) else str(payload)
            self._l1.drop(key) if key != "*" else self._l1.clear()

    async def bump_epoch(self, epoch: int) -> None:
        """Mass invalidation: new key generation, old one ages out via TTL."""
        self._epoch = epoch
        self._l1.clear()
        await self._guard(self._r.publish("cat:inval", "*"))

    # -- internals ---------------------------------------------------------
    async def _singleflight(self, key, loader):
        if (fut := self._inflight.get(key)) is not None:
            return await asyncio.shield(fut)          # local dedupe

        fut = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            got_lock = await self._guard(
                self._r.set(f"{key}:lock", "1", nx=True, px=5_000), default=True
            )
            if not got_lock:                          # another instance is filling
                await asyncio.sleep(0.05)
                if (entry := await self._l2_get(key)) is not None:
                    self._l1.put(key, entry)
                    fut.set_result(entry.value)
                    return entry.value

            async with self._origin_gate:             # bulkhead the origin
                value, version = await loader()

            await self._store(key, value, version)
            fut.set_result(value)
            return value
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
            with contextlib.suppress(Exception):
                await self._r.delete(f"{key}:lock")

    async def _store(self, key: str, value, version: int) -> None:
        ttl = self._negative_ttl if value is None else self._hard_ttl
        ttl *= random.uniform(0.9, 1.1)               # jitter: no synchronized expiry
        entry = Entry(value, version, time.monotonic(), min(self._soft_ttl, ttl))
        self._l1.put(key, entry)
        await self._guard(
            self._fill(
                keys=[key, self._lease(key)],
                args=[version, msgpack.packb(value, use_bin_type=True),
                      int(time.time() * 1000), int(ttl * 1000)],
            )
        )

    async def _refresh(self, key, loader) -> None:
        if key in self._inflight:
            return
        with contextlib.suppress(Exception):
            await self._singleflight(key, loader)

    async def _l2_get(self, key: str) -> Entry | None:
        return self._decode(await self._guard(self._r.hgetall(key)))

    def _decode(self, raw) -> Entry | None:
        if not raw:
            return None
        version = int(raw[b"v"])
        stored_at = time.monotonic() - max(0.0, time.time() - int(raw[b"t"]) / 1000)
        value = msgpack.unpackb(raw[b"d"], raw=False)
        return Entry(value, version, stored_at, self._soft_ttl)

    async def _guard(self, coro, default=None):
        """Cache failures degrade to misses; they never fail the request."""
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        except Exception:
            return default

    def _spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
```

Usage:

```python
cache = CatalogCache(redis, hard_ttl=3600, soft_ttl=300)
asyncio.create_task(cache.subscribe_invalidations())

async def read_product(pid: str) -> dict | None:
    async def load() -> tuple[dict | None, int]:
        row = await db.fetch_one("SELECT * FROM products WHERE id = $1", pid)
        return (dict(row), row["version"]) if row else (None, 0)
    return await cache.get("product", pid, load)

# from the CDC/outbox consumer
async def on_catalog_change(event) -> None:
    await cache.invalidate("product", event.product_id)
```

## 8. Tradeoffs I'm accepting

- **Eventual consistency, bounded.** A reader can see up to ~5s stale data (L1 TTL) if the invalidation broadcast is dropped, up to 1h if the whole event pipeline is down. If any field needs read-your-writes (e.g. a seller editing their own listing), route those requests around the cache with an explicit `no_cache` flag — don't weaken the global design for it.
- **L1 multiplies staleness surface** across N instances and consumes per-pod RAM. Worth it for the Zipfian head; drop L1 entirely if the SLO tightens below ~1s and you'd rather not reason about pub/sub delivery.
- **Redis pub/sub is at-most-once.** It's an optimization, not the correctness mechanism — that's why L1 also has a 5s TTL. If you need reliable L1 invalidation, move the fanout to the Kafka topic itself with per-instance consumer groups.
- **The version guard requires a monotonic version/`updated_at` on the origin row.** If the schema lacks one, the tombstone lease alone still covers the race, at the cost of a ~1s window where fills are suppressed after each write.

Before shipping: load-test the *bulk update* scenario (invalidate 50k hot keys at once) and the *cache-cold-start* scenario (Redis restarts under peak) — those two, not steady state, determine whether the design survives.