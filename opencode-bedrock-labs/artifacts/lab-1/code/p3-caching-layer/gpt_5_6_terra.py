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

