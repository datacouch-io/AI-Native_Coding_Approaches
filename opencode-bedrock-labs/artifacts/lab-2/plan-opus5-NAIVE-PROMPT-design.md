I'll start by exploring the codebase to understand the existing structure and find that comment.Let me read the core files.Now let me check the test fixtures and config.Let me verify the route-ordering trap I suspect, using a throwaway in-memory app (no workspace files touched).Confirmed the trap. Now let me validate the cursor SQL logic against the hardest acceptance test, in-memory:I have everything I need. Two things I verified empirically rather than assumed, and both change the implementation.

## Findings

**1. Route ordering is a hard trap.** The spec comment sits at the *bottom* of `main.py:97-109`, but `@app.get("/tasks/{task_id}")` is declared at `main.py:51`. Starlette matches routes in registration order with a `str` path convertor, so the `int` coercion on `task_id` happens *after* routing. I confirmed: declaring `/tasks/search` after `/tasks/{task_id}` returns **422 `int_parsing`**, not 404 — every single search test fails. The route must be registered *before* line 51.

**2. `limit` must be clamped, not validated.** `test_search.py:105-107` sends `limit=500` and asserts `status_code == 200`. The idiomatic `Query(20, ge=1, le=100)` returns 422 and fails that test. The cap has to be applied in code.

I also prototyped the cursor SQL in-memory against the concurrent-insert test and a synthetic all-identical-`created_at` case — both pass.

---

## Plan

### Sort key and cursor
Sort is `created_at DESC, id DESC`. The `id` tiebreaker is not optional: `created_at` is a `REAL` from `time.time()` (`main.py:43`), so ties are possible. The tests dodge this with `time.sleep(0.01)`, but without `id` a tie would silently skip or duplicate rows.

Cursor is an opaque base64url-encoded `"{created_at!r}:{id}"` of the page's last row (`repr` round-trips floats exactly in Python 3; unpadded, decoded with `rpartition(":")`). Keyset predicate:

```sql
(created_at < ? OR (created_at = ? AND id < ?))
```

Portable OR-form rather than SQLite row values — same result, no version floor.

### `next_cursor`
Query `LIMIT limit + 1`. If `limit + 1` rows come back there's another page: emit the cursor from row `limit - 1` and drop the extra. Otherwise `null`. No `COUNT(*)`, and it's correctly `null` on the final page rather than a dead cursor.

### Changes to `main.py`

**Move** the new endpoint above `get_task` (line 51). I'll replace the trailing comment block with a short pointer to the implementation so the file doesn't look like the feature is still missing.

```python
@app.get("/tasks/search")     # MUST precede /tasks/{task_id}
def search_tasks(
    q: Optional[str] = None,
    status: Optional[str] = None,
    min_priority: Optional[int] = None,
    max_priority: Optional[int] = None,
    limit: int = 20,
    cursor: Optional[str] = None,
):
```

Filter clauses, all parameterised, ANDed together:
- `q` → `LOWER(title) LIKE '%'||LOWER(?)||'%' ESCAPE '\'`, with `%`, `_`, `\` escaped in the input so `q="50%"` doesn't match everything
- `status` → `status = ?`
- `min_priority` / `max_priority` → `priority >= ?` / `priority <= ?`
- `limit` → `max(1, min(limit, 100))`

Response reuses the existing `row_to_dict` (`main.py:27`):

```json
{ "results": [ /* task objects */ ], "next_cursor": "eyJ..." | null }
```

A malformed or non-decodable `cursor` raises `HTTPException(400)` — distinguishable from a valid cursor that legitimately yields zero rows.

I'll match existing style: plain dict returns, no `response_model`, `get_conn()`/`conn.close()` as in the surrounding handlers.

### Verification
`.venv/bin/python -m pytest tests/ -v` — all 7 search tests plus the 5 existing CRUD tests. `test_crud.py` is regression cover, since adding a route above `/tasks/{task_id}` could shadow it.

---

Three decisions I'd like your call on before I write anything:

1. **Should the cursor embed the filters?** As planned, the client re-sends `q`/`status`/etc. alongside `cursor`; changing filters mid-page-walk gives coherent-but-arbitrary results. Embedding a filter fingerprint and rejecting mismatches with a 400 is stricter and more correct, but goes beyond the spec and the tests. Minimal, or strict?

2. **`limit=0` or negative.** The cap at 100 must clamp (test-mandated). The lower bound is untested — clamp to 1 for symmetry, or 422? I've assumed clamp.

3. **Index.** `CREATE INDEX IF NOT EXISTS idx_tasks_created_at_id ON tasks(created_at DESC, id DESC)` in `db.py:init_db` makes the keyset seek an index scan instead of a sort. Correctness is unaffected at test scale. Include it, or keep the diff confined to `main.py`?