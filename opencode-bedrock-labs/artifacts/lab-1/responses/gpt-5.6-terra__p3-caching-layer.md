**Approach**

Use a two-tier, cache-aside design:

- **L1 cache:** Small in-process LRU cache for the hottest products, with a short TTL (for example, 15-60 seconds).
- **L2 cache:** Shared Redis cluster containing product records, with a longer TTL (for example, 10-30 minutes plus jitter).
- **Database:** Source of truth.

Cache-aside is the appropriate primary pattern here because catalog updates are infrequent, reads dominate, and it avoids routing every write through the cache. On a read miss, the service loads from the database and populates the cache.

Use **write-side invalidation**, not write-through:

1. Write the updated product to the database transactionally.
2. After the transaction commits, invalidate the shared product key.
3. Publish an invalidation event so every service instance evicts its local L1 entry.
4. The next read repopulates L2 from the database.

For a catalog whose correctness requirements are more strict, use a product version in cached values and compare it with the database/version carried in invalidation events. This prevents a slow, in-flight cache fill from overwriting newer cache data.

**Eviction Policy**

Configure Redis with `allkeys-lfu` if it is dedicated primarily to catalog caching:

- Product popularity is usually skewed: a small subset of products gets most reads.
- LFU retains frequently requested products better than LRU during large catalog scans or temporary bursts.
- If Redis is shared with workloads that require strict key retention, isolate the catalog cache into its own Redis cluster or logical deployment rather than relying on a global eviction policy.

Use expiration even with explicit invalidation:

- Protects against missed invalidation events.
- Reclaims stale/unread entries.
- Adds a bounded-staleness fallback.

Add randomized TTL jitter to avoid many keys expiring simultaneously:

```text
base TTL: 20 minutes
jitter:   0-2 minutes
```

**Invalidation Strategy**

Keys:

```text
catalog:product:{productId}
catalog:product:missing:{productId}
```

Cache normal records with a moderate TTL. Negative-cache nonexistent products briefly, such as 30-60 seconds, to protect the database from repeated requests for invalid IDs.

For updates:

```text
database transaction commits
  -> delete Redis product key
  -> publish product-invalidated event
  -> each instance removes its L1 copy
```

The Redis deletion is deliberately performed after the database commit. Invalidating before commit can cause another reader to refill the cache from old database state.

The unavoidable failure window between a committed database update and invalidation should be handled with:

- A transactional outbox written in the same database transaction as the catalog change.
- An asynchronous outbox publisher that reliably performs Redis invalidation and emits the invalidation event.
- TTL as a final safety bound if Redis or messaging is temporarily unavailable.

**Core TypeScript Logic**

This example assumes:

- `redis` is a Redis client with `get`, `set`, `del`, `publish`, and `subscribe`.
- `productRepository` reads and updates the source-of-truth database.
- An L1 cache implementation is provided by `lru-cache`.

```ts
import { LRUCache } from "lru-cache";

type Product = {
  id: string;
  name: string;
  priceCents: number;
  available: boolean;
  version: number;
  updatedAt: string;
};

type CachedProduct = {
  product: Product | null;
  version: number;
};

interface RedisClient {
  get(key: string): Promise<string | null>;
  set(
    key: string,
    value: string,
    options: { EX: number; NX?: boolean },
  ): Promise<unknown>;
  del(key: string): Promise<number>;
  publish(channel: string, message: string): Promise<number>;
  subscribe(channel: string, listener: (message: string) => void): Promise<void>;
}

interface ProductRepository {
  findById(id: string): Promise<Product | null>;

  transaction<T>(work: () => Promise<T>): Promise<T>;
  update(id: string, update: Partial<Product>): Promise<Product>;

  // Prefer an outbox write here in production.
  insertOutboxEvent(event: {
    type: "product.invalidated";
    productId: string;
    version: number;
  }): Promise<void>;
}

const PRODUCT_TTL_SECONDS = 20 * 60;
const NEGATIVE_TTL_SECONDS = 45;
const MAX_TTL_JITTER_SECONDS = 2 * 60;
const LOCK_TTL_SECONDS = 5;

const productL1 = new LRUCache<string, CachedProduct>({
  max: 50_000,
  ttl: 30_000,
});

function productCacheKey(productId: string): string {
  return `catalog:product:${productId}`;
}

function productLockKey(productId: string): string {
  return `catalog:product:lock:${productId}`;
}

function ttlWithJitter(baseSeconds: number): number {
  return baseSeconds + Math.floor(Math.random() * MAX_TTL_JITTER_SECONDS);
}

function serialize(value: CachedProduct): string {
  return JSON.stringify(value);
}

function deserialize(value: string): CachedProduct {
  return JSON.parse(value) as CachedProduct;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
```

```ts
export class ProductCatalogCache {
  constructor(
    private readonly redis: RedisClient,
    private readonly productRepository: ProductRepository,
  ) {}

  async getProduct(productId: string): Promise<Product | null> {
    const l1Value = productL1.get(productId);
    if (l1Value) {
      return l1Value.product;
    }

    const cacheKey = productCacheKey(productId);
    const redisValue = await this.redis.get(cacheKey);

    if (redisValue) {
      const cached = deserialize(redisValue);
      productL1.set(productId, cached);
      return cached.product;
    }

    return this.loadAndCacheProduct(productId);
  }

  private async loadAndCacheProduct(productId: string): Promise<Product | null> {
    const lockKey = productLockKey(productId);

    // A short-lived distributed lock reduces cache stampedes when a hot key expires.
    const lockAcquired = await this.redis.set(lockKey, "1", {
      EX: LOCK_TTL_SECONDS,
      NX: true,
    });

    if (!lockAcquired) {
      // Another request is likely loading the item. Wait briefly for its cache fill.
      for (let attempt = 0; attempt < 3; attempt++) {
        await sleep(25 + Math.floor(Math.random() * 25));

        const cachedValue = await this.redis.get(productCacheKey(productId));
        if (cachedValue) {
          const cached = deserialize(cachedValue);
          productL1.set(productId, cached);
          return cached.product;
        }
      }

      // Do not wait indefinitely. A database read is preferable to a slow request.
      return this.readDatabaseAndBestEffortCache(productId);
    }

    try {
      // Recheck after acquiring the lock: another request may have filled it first.
      const cachedValue = await this.redis.get(productCacheKey(productId));
      if (cachedValue) {
        const cached = deserialize(cachedValue);
        productL1.set(productId, cached);
        return cached.product;
      }

      return this.readDatabaseAndBestEffortCache(productId);
    } finally {
      await this.redis.del(lockKey);
    }
  }

  private async readDatabaseAndBestEffortCache(
    productId: string,
  ): Promise<Product | null> {
    const product = await this.productRepository.findById(productId);

    const cached: CachedProduct = {
      product,
      version: product?.version ?? 0,
    };

    const ttl = product ? ttlWithJitter(PRODUCT_TTL_SECONDS) : NEGATIVE_TTL_SECONDS;

    // A cache failure must not fail a catalog read when the database succeeded.
    try {
      await this.redis.set(productCacheKey(productId), serialize(cached), {
        EX: ttl,
      });
    } catch {
      // Record metrics/logs here; serve the authoritative database result.
    }

    productL1.set(productId, cached);
    return product;
  }

  async invalidateProduct(productId: string, version: number): Promise<void> {
    productL1.delete(productId);

    try {
      await this.redis.del(productCacheKey(productId));
      await this.redis.publish(
        "catalog.product.invalidated",
        JSON.stringify({ productId, version }),
      );
    } catch {
      // This should be retried by a durable outbox worker in production.
      // TTL remains the fallback bound on stale data.
    }
  }

  async updateProduct(
    productId: string,
    update: Partial<Product>,
  ): Promise<Product> {
    const product = await this.productRepository.transaction(async () => {
      const updated = await this.productRepository.update(productId, update);

      // Durable delivery is important: do not depend only on a best-effort publish.
      await this.productRepository.insertOutboxEvent({
        type: "product.invalidated",
        productId,
        version: updated.version,
      });

      return updated;
    });

    // Low-latency best effort. The outbox processor guarantees eventual delivery.
    await this.invalidateProduct(product.id, product.version);

    return product;
  }
}
```

Each application instance subscribes to invalidations and clears only its L1 entry:

```ts
export async function startProductInvalidationSubscriber(
  subscriber: RedisClient,
): Promise<void> {
  await subscriber.subscribe("catalog.product.invalidated", (message) => {
    const event = JSON.parse(message) as {
      productId: string;
      version: number;
    };

    const local = productL1.get(event.productId);

    // Only remove a local entry if it is not newer than the invalidation event.
    if (!local || local.version <= event.version) {
      productL1.delete(event.productId);
    }
  });
}
```

A durable outbox worker should independently process committed invalidation events, retrying failures until Redis invalidation and publication succeed:

```ts
async function processProductInvalidationEvent(
  redis: RedisClient,
  event: { productId: string; version: number },
): Promise<void> {
  await redis.del(productCacheKey(event.productId));

  await redis.publish(
    "catalog.product.invalidated",
    JSON.stringify(event),
  );
}
```

This design provides low latency for hot products, protects the database during cache misses, avoids cache stampedes, keeps local instances coherent, and bounds stale-data exposure when the invalidation pipeline has a transient failure.