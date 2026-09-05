# Three tasks, increasing difficulty

The point of the battery is the gradient. A task every tier passes tells you
nothing about tiering; a task every tier fails tells you nothing either. These
three are chosen so the tiers separate somewhere in the middle.

---

## T1 — `chunk(seq, size)` (easy)

```python
def chunk(seq: list, size: int) -> list[list]: ...
```

1. Split `seq` into consecutive sublists of length `size`.
2. The final chunk may be shorter; never pad it.
3. An empty `seq` returns `[]`.
4. `size` must be a positive integer, else raise `ValueError`.
5. The input list must not be mutated.

---

## T2 — `compare_semver(a, b)` (medium)

```python
def compare_semver(a: str, b: str) -> int: ...
```

Returns `-1` if `a < b`, `0` if equal, `1` if `a > b`.

1. Versions are `MAJOR.MINOR.PATCH`, each a non-negative integer without
   leading zeros. Compare numerically, left to right.
2. A version may carry a pre-release suffix: `1.0.0-alpha.1`.
3. **A pre-release version is LOWER than the same version without one**:
   `1.0.0-alpha` < `1.0.0`.
4. Pre-release identifiers are compared dot-separated, left to right. A purely
   numeric identifier is compared numerically; otherwise ASCII order. A numeric
   identifier always ranks LOWER than a non-numeric one.
5. A longer pre-release chain outranks its own prefix: `1.0.0-alpha` <
   `1.0.0-alpha.1`.
6. Build metadata (`+build.5`) is ignored entirely for comparison.
7. Anything malformed raises `ValueError`.

---

## T3 — `backoff_schedule(...)` (hard)

```python
def backoff_schedule(attempts: int, base: float, factor: float,
                     cap: float, max_elapsed: float) -> list[float]: ...
```

Produce the list of delays before each retry.

1. Delay for attempt `i` (0-indexed) is `base * (factor ** i)`.
2. Every delay is clamped to at most `cap`.
3. The schedule stops early once the CUMULATIVE delay would exceed
   `max_elapsed`. The delay that would breach it is truncated to exactly the
   remaining budget, and if that remainder is `0`, it is omitted entirely.
4. At most `attempts` delays are returned.
5. Every returned delay is rounded to 3 decimal places.
6. `attempts` must be a non-negative integer; `base`, `factor`, `cap` and
   `max_elapsed` must be non-negative numbers. Otherwise raise `ValueError`.
7. `attempts == 0` returns `[]`.
