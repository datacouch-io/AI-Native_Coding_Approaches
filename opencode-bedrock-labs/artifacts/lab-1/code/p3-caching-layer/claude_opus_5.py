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
