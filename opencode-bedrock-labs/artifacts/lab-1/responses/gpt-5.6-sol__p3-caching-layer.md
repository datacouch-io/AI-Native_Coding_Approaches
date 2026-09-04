## Approach

Use a shared Redis cluster as the primary cache, with the database remaining the source of truth.

- **Read strategy:** Cache-aside. Reads check Redis first, then load from the database and populate Redis on a miss.
- **Write strategy:** Update the database first, then publish a versioned catalog-change event. Consumers proactively replace or invalidate the cached entry.
- **Eviction policy:** Redis `allkeys-lfu`, because catalog traffic is generally skewed toward popular products.
- **Expiration:** Approximately 6 hours for product metadata, with TTL jitter to prevent synchronized expiration. Keep entries physically for up to 24 hours to permit stale-on-error responses.
- **Negative caching:** Cache missing products for around 30 seconds to protect against repeated requests for invalid IDs.
- **Stampede protection:** Use a short-lived distributed lock and double-check the cache after obtaining it.
- **Consistency:** Every product mutation increments a monotonic version. Cache updates use compare-and-set so delayed reads or out-of-order events cannot overwrite newer data.
- **Reliability:** Create an outbox event in the same database transaction as the catalog update. This ensures cache refreshes are retried if Redis or the event broker is temporarily unavailable.

For mutable operational data such as inventory, availability, or rapidly changing prices, I would use separate keys and shorter TTLs rather than putting them in the long-lived product metadata entry.

## Why Cache-Aside

True write-through would make successful database writes depend on Redis availability and would cache products that may never be read. Cache-aside is a better fit for a read-heavy catalog:

1. The database remains authoritative.
2. Cache failures do not prevent catalog updates.
3. Only requested products consume cache capacity.
4. Post-commit events provide fast invalidation without requiring a short TTL.

The write path performs a best-effort immediate cache refresh, but a transactional outbox is responsible for guaranteed eventual refresh.

## Invalidation Strategy

For an update:

1. Increment the product's version in the database.
2. Commit the product update and an outbox event atomically.
3. Best-effort refresh Redis immediately after the commit.
4. Have the outbox consumer repeat that refresh until successful.
5. Apply the cache update only when its version is at least as new as the cached version.

For deletion, publish a versioned tombstone rather than simply deleting the key. This prevents an older in-flight database read from repopulating the deleted product.

Versioning also handles this race safely:

```text
Reader loads version 10 from DB
Writer commits version 11
Writer caches version 11
Reader attempts to cache version 10
Redis rejects version 10
```

## Core TypeScript Logic

```ts
interface Product {
  id: string;
  name: string;
  description: string;
  categoryId: string;
  version: number;
}

interface ProductSnapshot {
  // null represents a deleted or nonexistent product.
  product: Product | null;
  version: number;
}

interface ProductRepository {
  findSnapshot(id: string): Promise<ProductSnapshot>;
}

interface RedisClient {
  get(key: string): Promise<string | null>;
  del(key: string): Promise<number>;

  set(
    key: string,
    value: string,
    options?: {
      EX?: number;
      PX?: number;
      NX?: boolean;
    },
  ): Promise<"OK" | null>;

  eval(
    script: string,
    options: {
      keys: string[];
      arguments: string[];
    },
  ): Promise<unknown>;
}

interface CacheEnvelope {
  value: Product | null;
  version: number;
  freshUntil: number;
}

const POSITIVE_FRESH_TTL_SECONDS = 6 * 60 * 60;
const POSITIVE_STORAGE_TTL_SECONDS = 24 * 60 * 60;

const NEGATIVE_FRESH_TTL_SECONDS = 30;
const NEGATIVE_STORAGE_TTL_SECONDS = 5 * 60;

const FILL_LOCK_MS = 3_000;

const VERSIONED_SET_SCRIPT = `
local current = redis.call("GET", KEYS[1])

if current then
  local currentValue = cjson.decode(current)
  local incomingVersion = tonumber(ARGV[2])
  local currentVersion = tonumber(currentValue["version"])

  if currentVersion > incomingVersion then
    return 0
  end
end

redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[3])
return 1
`;

const RELEASE_LOCK_SCRIPT = `
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end

return 0
`;

export class ProductCatalogCache {
  constructor(
    private readonly redis: RedisClient,
    private readonly repository: ProductRepository,
  ) {}

  async getProduct(id: string): Promise<Product | null> {
    const key = this.productKey(id);
    let cached = await this.readEnvelope(key);

    if (cached && cached.freshUntil > Date.now()) {
      return cached.value;
    }

    const lockKey = `${key}:fill`;
    const lockToken = crypto.randomUUID();

    const acquired = await this.redis.set(lockKey, lockToken, {
      NX: true,
      PX: FILL_LOCK_MS,
    });

    if (acquired === "OK") {
      try {
        // Another request or update event may have populated the cache
        // immediately before this request obtained the lock.
        const latest = await this.readEnvelope(key);

        if (latest && latest.freshUntil > Date.now()) {
          return latest.value;
        }

        try {
          const snapshot = await this.repository.findSnapshot(id);
          await this.cacheSnapshot(snapshot);
          return snapshot.product;
        } catch (error) {
          // Product metadata can usually tolerate bounded staleness during
          // a transient database failure.
          if (cached) {
            return cached.value;
          }

          throw error;
        }
      } finally {
        await this.redis.eval(RELEASE_LOCK_SCRIPT, {
          keys: [lockKey],
          arguments: [lockToken],
        });
      }
    }

    // Serve stale data while another request refreshes it.
    if (cached) {
      return cached.value;
    }

    // On a cold miss, briefly wait for the lock owner.
    for (let attempt = 0; attempt < 4; attempt++) {
      await sleep(40);

      cached = await this.readEnvelope(key);
      if (cached) {
        return cached.value;
      }
    }

    // Do not make correctness depend on the lock. If its owner failed or the
    // database query is slow, query the source of truth directly.
    const snapshot = await this.repository.findSnapshot(id);
    await this.cacheSnapshot(snapshot);
    return snapshot.product;
  }

  /**
   * Called after a product transaction commits and by the transactional
   * outbox consumer. Safe to invoke repeatedly and out of order.
   */
  async onProductChanged(snapshot: ProductSnapshot): Promise<void> {
    await this.cacheSnapshot(snapshot);
  }

  private async cacheSnapshot(snapshot: ProductSnapshot): Promise<void> {
    const isNegative = snapshot.product === null;
    const freshTtl = isNegative
      ? NEGATIVE_FRESH_TTL_SECONDS
      : withJitter(POSITIVE_FRESH_TTL_SECONDS);

    const storageTtl = isNegative
      ? NEGATIVE_STORAGE_TTL_SECONDS
      : withJitter(POSITIVE_STORAGE_TTL_SECONDS);

    const envelope: CacheEnvelope = {
      value: snapshot.product,
      version: snapshot.version,
      freshUntil: Date.now() + freshTtl * 1_000,
    };

    await this.redis.eval(VERSIONED_SET_SCRIPT, {
      keys: [this.productKeyFromSnapshot(snapshot)],
      arguments: [
        JSON.stringify(envelope),
        String(snapshot.version),
        String(storageTtl),
      ],
    });
  }

  private async readEnvelope(key: string): Promise<CacheEnvelope | null> {
    const raw = await this.redis.get(key);

    if (raw === null) {
      return null;
    }

    try {
      return JSON.parse(raw) as CacheEnvelope;
    } catch {
      // Recover automatically from malformed or incompatible cached data.
      await this.redis.del(key);
      return null;
    }
  }

  private productKey(id: string): string {
    return `catalog:product:${id}`;
  }

  private productKeyFromSnapshot(snapshot: ProductSnapshot): string {
    if (snapshot.product === null) {
      // A real implementation should include the product ID separately on
      // tombstone events, for example: { id, product: null, version }.
      throw new Error("Tombstone snapshot must include a product ID");
    }

    return this.productKey(snapshot.product.id);
  }
}

function withJitter(ttlSeconds: number): number {
  // Spread expiration over +/-10% to avoid synchronized cache misses.
  const factor = 0.9 + Math.random() * 0.2;
  return Math.round(ttlSeconds * factor);
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}
```

In production, I would define the snapshot with an explicit ID so tombstones can be cached cleanly:

```ts
interface ProductSnapshot {
  id: string;
  product: Product | null;
  version: number;
}
```

Then `cacheSnapshot` can always use `catalog:product:${snapshot.id}`.

## Operational Settings

Recommended starting settings:

```text
Redis eviction:       allkeys-lfu
Positive fresh TTL:   6 hours +/- 10%
Positive storage TTL: 24 hours +/- 10%
Negative fresh TTL:   30 seconds
Negative storage TTL: 5 minutes
Fill lock:             3 seconds
```

Monitor cache hit rate, database fallback rate, p95 latency, evictions, memory utilization, lock contention, stale responses, and outbox event lag. Cache capacity should be sized from serialized entry size, expected hot working set, replication overhead, and at least 20–30% operational headroom.