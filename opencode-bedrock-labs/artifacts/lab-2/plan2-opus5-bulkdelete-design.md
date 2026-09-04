I'll start by reading the test spec and the existing app code.Now let me empirically confirm the route-ordering hazard applies to `DELETE` the same way it did to `GET /tasks/search`, without touching the project's DB.Confirmed the hazard reproduces exactly. Let me re-check the bare-`DELETE` rowcount claim properly (my first probe had only one row left, so it wasn't a valid test).I've read everything and probed the two things worth verifying. Here's what I found and how I'd build it.

## What the spec pins down

From `tests/test_bulk_delete.py`, the contract is narrow and exact:

| Behavior | Requirement |
|---|---|
| Method + path | `DELETE /tasks/bulk` |
| Params | query string (`params=`), not a body |
| Filters | `status` (exact), `max_priority` (inclusive `<=`) |
| Multiple filters | ANDed (test at line 36) |
| Success | `200` + body **exactly** `{"deleted_count": N}` |
| No filters at all | `400`, and **nothing deleted** |
| Matches nothing | `200` + `{"deleted_count": 0}` |

Note the body assertions use `==`, not subset checks — so no extra keys like `matched_ids` or `filters_applied`.

## The thing that will bite this: yes, it's the same trap

`DELETE /tasks/{task_id}` is already declared at `main.py:218`. FastAPI does **not** compile `task_id: int` into Starlette's `int` path convertor (which would regex-reject non-digits); it registers the path as `[^/]+` and coerces during validation. So `/tasks/bulk` matches `{task_id}` first and dies in validation — identical to the `/tasks/search` problem documented at `main.py:99-102`.

I confirmed it rather than assuming:

```
WRONG ORDER -> 422 {'detail': [{'type': 'int_parsing', 'loc': ['path','task_id'],
                    'input': 'bulk'}]}
RIGHT ORDER -> 200 {'deleted_count': 0}
still works  -> 204   (DELETE /tasks/7 unaffected)
```

So the failure mode is a `422`, not a `405` or `404` — which is worth knowing because a `422` on a DELETE looks like a payload problem and sends you debugging the wrong file.

### Four more hazards specific to this endpoint

1. **The falsy-zero trap** (this endpoint's version of the `limit` trap). The 400 guard must be `if status is None and max_priority is None`. Writing `if not status and not max_priority` makes `max_priority=0` — a legitimate filter — fall through to a `400`. Worse, if the guard is ever inverted, that same bug turns "delete where priority <= 0" into "delete everything."

2. **Don't copy `status_code=204`** from `delete_task` at `main.py:218`. The tests demand `200` *with* a body; `@app.delete` already defaults to 200. A 204 with a body is also just broken at the ASGI layer.

3. **Connection leak on the error path.** `main.py:203-205` shows the author already had to hand-close the connection before raising inside `update_task`. Sidestep it entirely: raise the `400` **before** calling `get_conn()`. Then there is no error path holding a handle.

4. **Function name collision.** Name it `bulk_delete_tasks`; `delete_task` is taken at module scope and a redefinition would silently clobber the route handler.

I also checked whether `cursor.rowcount` is trustworthy for the count, since SQLite's truncate optimization historically muddied this. On this env (SQLite 3.53.4 / Python 3.14.6) it's accurate — `2` for a matching `WHERE`, `0` for no match, and correct even for a bare `DELETE`. So a single `DELETE` + `rowcount` works; no need for a `SELECT COUNT(*)` first, which would be two statements and racy.

## Proposed implementation

Placement: insert immediately after `search_tasks` (after `main.py:178`), i.e. **above** `GET /tasks/{task_id}`. It only strictly needs to precede line 218, but putting it here establishes a single invariant for the file — *all literal `/tasks/<word>` routes precede all `/tasks/{param}` routes* — which is what stops this from recurring a third time. Carry a comment in the style of the existing one, since that comment is the only reason the search route hasn't regressed.

```python
# NOTE: like /tasks/search above, this static route MUST be declared before
# DELETE /tasks/{task_id}. Starlette matches in declaration order and "bulk"
# fails the int coercion for {task_id} -- if this moves below delete_task,
# every DELETE /tasks/bulk returns 422 instead of matching here.
@app.delete("/tasks/bulk")
def bulk_delete_tasks(
    status: Optional[str] = None,
    max_priority: Optional[int] = None,
):
    """Delete every task matching the given filters (ANDed). Returns the count.

    At least one filter is required: an unfiltered call would silently wipe
    the table, so it is rejected with 400 rather than treated as "match all".
    """
    # `is None`, not falsiness: max_priority=0 is a real filter.
    if status is None and max_priority is None:
        raise HTTPException(
            status_code=400,
            detail="at least one filter (status, max_priority) is required",
        )

    fragments = []
    params: list = []
    if status is not None:
        fragments.append("status = ?")
        params.append(status)
    if max_priority is not None:
        fragments.append("priority <= ?")
        params.append(max_priority)

    sql = "DELETE FROM tasks WHERE " + " AND ".join(fragments)

    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    return {"deleted_count": deleted}
```

The fragment-building mirrors `search_tasks` (`main.py:138-159`) so the filter semantics stay consistent and everything stays parameterized. Deliberately *not* following `update_task:209`, which f-strings column names — safe there only because the keys come from a Pydantic model, and not a pattern to spread to a destructive statement.

Verification: `pytest tests/ -q` — all 5 new tests plus the existing 13 in `test_crud.py`/`test_search.py`, to confirm the insertion didn't disturb `GET /tasks/{task_id}` or `DELETE /tasks/{task_id}`.

## Two decisions I'd like your call on

**1. Filter set — minimal, or symmetric with `/tasks/search`?** I've scoped it to `status` + `max_priority` (exactly what the tests exercise). The consistency argument says mirror all four search filters, but I'd push back on that for a destructive endpoint: `min_priority=1` alone would satisfy the "at least one filter" guard while deleting essentially the whole table, and a `q` substring match makes it easy to delete far more than intended. Minimal now, widen deliberately later — but tell me if you'd rather have parity.

**2. Should I add a route-ordering regression test?** This is the second time this exact trap has landed. A one-line test asserting `DELETE /tasks/bulk` doesn't return 422 would convert the load-bearing comment into something enforced. Cheap, but it's outside the given acceptance spec, so I won't add it unless you want it.

Want me to proceed with the minimal filter set as written?