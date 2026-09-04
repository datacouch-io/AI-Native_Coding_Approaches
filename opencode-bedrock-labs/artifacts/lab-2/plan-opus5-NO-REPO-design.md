I'll start by exploring the existing codebase to understand what's already there.## Findings

The working directory `/private/tmp/lab2-no-repo-test` is **completely empty**. That changes the shape of this task in two important ways:

1. **There is no `main.py`**, so the "SPEC in main.py's trailing comment" that your acceptance tests are written against doesn't exist yet. This is a greenfield build, not an addition to an existing API.
2. **There is no `conftest.py`**, so the `client` fixture every test depends on must be written too.

Environment: Python 3.14.6 (Homebrew) only — no 3.12/3.13, no `uv`, no `pyenv`. `fastapi`, `pydantic`, `pytest`, `httpx` are all absent and Homebrew Python is PEP-668 externally-managed, so a venv is required. Bundled SQLite is 3.53.4, which supports row-value comparisons (`(a,b) < (?,?)`), though I'd still write the expanded form for portability.

## Design

**Ordering.** `ORDER BY created_at DESC, id DESC`. The `id` tiebreak is not optional: `test_search_limit_capped_at_100` inserts 120 tasks with no sleep, so `created_at` values will collide and a single-column sort would be non-deterministic — which breaks cursor correctness (silent skips/duplicates). A total order is a prerequisite for keyset pagination.

**Cursor.** Keyset (seek) pagination, not `OFFSET`. The cursor is an opaque base64url token encoding the `(created_at, id)` of the last row returned. Page N+1 asks for rows strictly "after" that anchor in the sort order:

```sql
(created_at < :c_created_at) OR (created_at = :c_created_at AND id < :c_id)
```

This is what makes `test_search_pagination_stable_under_concurrent_insert` pass: the mid-pagination insert has the newest `created_at`, so it sorts *before* the anchor and is naturally excluded by the `<` predicate. No shift, no duplicate, no skip.

**`next_cursor`.** Fetch `limit + 1` rows; if the extra row exists, a next page exists and `next_cursor` is built from the last *returned* row; otherwise `null`. This avoids handing back a cursor that leads to an empty page.

**Timestamps.** Microsecond-precision UTC ISO-8601, zero-padded so lexicographic string order equals chronological order. The tests' `time.sleep(0.01)` only yields distinct ordering if resolution is sub-second — second-granularity timestamps would collapse all 5 tasks and fail test 4 and 5.

## Traps in the acceptance tests

- **`limit=500` must return `200`, not `422`.** The test asserts `status_code == 200` and `len(results) <= 100`. So the cap must be applied by clamping in the handler (`min(limit, 100)`), **not** via `Query(..., le=100)`, which would reject the request. This is the single easiest way to fail the suite while looking correct.
- **`POST /tasks` must accept `{"title": ...}` alone** (`test_search_limit_capped_at_100` omits status/priority), so those fields need defaults `"open"` and `3`.
- **Per-test DB isolation is mandatory.** Tests assert exact counts (`len(results) == 1`), so leaked rows from a prior test fail them. The `client` fixture gets a fresh temp-file SQLite DB per test via a FastAPI dependency override. A module-level global DB will fail the suite.
- **`q` needs LIKE-wildcard escaping** (`%`, `_`, `\` with `ESCAPE`), otherwise `q=100%` matches everything.

## Plan

1. Create a venv at `.venv` and install `fastapi`, `uvicorn`, `pytest`, `httpx`.
2. Write `main.py`: SQLite schema + `POST /tasks` + `GET /tasks` + `GET /tasks/search` with the keyset cursor, plus the trailing SPEC comment your tests reference.
3. Write `conftest.py`: `client` fixture with a per-test temp DB and dependency override.
4. Write `tests/test_search.py` with your acceptance test file verbatim.
5. Run the suite; confirm all 6 pass. Then sanity-check the negative case (that an `OFFSET` implementation would fail test 5) to prove the test is actually load-bearing.

## Questions before I build

1. **Greenfield confirmed?** I'll write the base `POST /tasks` API and the SPEC comment myself, inferring the contract from the tests. If you have the intended `main.py` / SPEC text from the lab, paste it and I'll match it exactly rather than guessing field names and defaults.
2. **Layout** — `main.py` + `conftest.py` at root, tests in `tests/test_search.py`? Or all flat at root?
3. **Invalid cursor behavior** — `400 Bad Request` (my preference, fails loudly) or silently ignore and return page 1?
4. **Filter binding** — should the cursor embed a fingerprint of `q`/`status`/priority range and `400` if the caller changes filters mid-pagination? It's stricter and catches a real client bug class, but adds complexity beyond what the tests require. My default is to skip it and document the behavior as undefined.