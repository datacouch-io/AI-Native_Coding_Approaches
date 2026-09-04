I'll read both files first.Let me verify two behaviors that materially affect the design (route matching order and SQLite `LIKE` semantics) without touching the repo.Both files read, plus `db.py`, `conftest.py`, and `test_crud.py` for context. I also empirically verified two things that change the design. Here is the design document.

---

# Design: `GET /tasks/search`

## 0. Verified environment facts (do not re-litigate these)

| Fact | Verification |
|---|---|
| `/tasks/search` returns **422** if declared after `GET /tasks/{task_id}` | Confirmed by probe: Starlette matches routes in declaration order; `"search"` fails the `int` coercion on `task_id`. |
| Declaring `/tasks/search` **before** `/tasks/{task_id}` keeps both working (200/200) | Confirmed by probe. |
| SQLite's default `LIKE` is already case-insensitive for ASCII | `title LIKE '%report%'` matched `'Write REPORT'`. |
| SQLite `LOWER()` is ASCII-only, so it does **not** add Unicode case-folding | `LOWER(title) LIKE LOWER('%CAFÉ%')` matched nothing. |
| Un-escaped `_`/`%` in user input act as wildcards | `LIKE '%rep_ort%'` matched literal `rep_ort`. |
| `created_at` is `REAL` (IEEE-754 double) from `time.time()` | `db.py:23`, `main.py:43`. |
| `id` is `INTEGER PRIMARY KEY AUTOINCREMENT` — unique, monotonically increasing | `db.py:18`. |

---

## 1. Why offset-based pagination fails this test

Sort order is `created_at DESC` (newest first). `OFFSET n` means *"discard the first n rows of the result set as it exists at the moment this query runs."* It is an **ordinal position in a mutable sequence**, and insert/delete activity renumbers that sequence.

Walk the exact test in `test_search_pagination_stable_under_concurrent_insert`. Rows get ids 1–5 (`original[0]`…`original[4]`), ascending `created_at`.

**Page 1** — result set ordered `created_at DESC` is `[5, 4, 3, 2, 1]`. `LIMIT 2 OFFSET 0` → `[5, 4]`. Assertion at line 82 passes.

**Concurrent insert** — `"Inserted mid-pagination"` gets id 6 and the largest `created_at`, so it sorts to **position 0**. The result set is now `[6, 5, 4, 3, 2, 1]`. Every previously-seen row shifted **one position to the right**.

**Page 2** — `LIMIT 2 OFFSET 2` reads positions 2–3 of the *new* sequence → `[4, 3]`. The test demands `[3, 2]`. It fails, and it fails in the worst way: **id 4 is served twice** (it was on page 1), and when the caller reaches the end, id 1 will fall off past the last offset and be **served zero times**. A deletion above the window produces the mirror-image bug — rows shift left, and one row is silently skipped.

The defect is not "offset is slow." It is that the offset number the client holds refers to a coordinate system the server is free to renumber between requests. There is no value the client can send that survives renumbering, because the client is sending a *count*.

**What the cursor fixes.** A keyset cursor sends the **sort-key value of the last row already delivered**, and page 2 is expressed as a `WHERE` predicate — *"rows whose sort key is strictly past this anchor"* — instead of a positional skip. Sort-key values are properties of the data, not of the collection, so nothing renumbers them:

- The inserted row (id 6) has `created_at` **greater** than the anchor, so it sorts *before* the anchor and is excluded by the predicate. It cannot shift page 2.
- Rows already delivered (5, 4) have `created_at >= ` anchor and are likewise excluded — no duplicates.
- Deleting an already-passed row changes no surviving row's key — no skips.

Page 2 becomes `[3, 2]` regardless of concurrent write volume. Note the honest scope: keyset pagination guarantees **no duplicates and no skips relative to the original ordering**; it does not hide rows inserted *behind* the cursor (older `created_at`), which is the correct and desired behavior for a newest-first feed.

---

## 2. Sort key and cursor predicate

The sort key must be a **total order**, otherwise rows that tie are ordered nondeterministically between requests and the cursor can skip or repeat them. `created_at` alone is **not** sufficient: it is a float from `time.time()`, and `test_search_limit_capped_at_100` inserts 120 rows in a tight loop with no `sleep`. Ties are possible.

**Canonical sort key: `(created_at DESC, id DESC)`.** `id` is unique, so the composite is total. The tiebreaker must descend in the same direction as the primary key, or the predicate below is wrong.

**`ORDER BY` clause, used identically on every request (with or without a cursor):**

```sql
ORDER BY created_at DESC, id DESC
```

**Cursor predicate**, given anchor `(:c_created_at, :c_id)`:

```sql
(created_at < :c_created_at OR (created_at = :c_created_at AND id < :c_id))
```

Emit it as a single parenthesized group with exactly three bound parameters in the order `(:c_created_at, :c_created_at, :c_id)`. The outer parentheses are mandatory — dropping them lets `OR` bind loosely against the other `AND`-joined filters and the endpoint will silently return wrong rows.

The SQLite row-value form `(created_at, id) < (:c_created_at, :c_id)` is equivalent on SQLite ≥ 3.15. Use the explicit `OR` form; it is version-agnostic and reads unambiguously.

---

## 3. Cursor encoding

**Payload (JSON object, exactly these three keys):**

```json
{"v": 1, "created_at": 1725441234.567891, "id": 4}
```

**Wire format:** UTF-8 encode the JSON, then **base64url** (RFC 4648 §5, `-`/`_` alphabet), then **strip all `=` padding**. The result is the opaque `next_cursor` string.

Rationale for each choice:
- **base64url, not standard base64** — the cursor travels in a query string; `+` and `/` require percent-encoding and get mangled by careless clients.
- **Padding stripped** — bare `=` in query strings is a delimiter character. The decoder re-adds padding: append `"=" * (-len(s) % 4)` before decoding.
- **Opaque/encoded rather than two plain query params** — it keeps the pagination contract server-owned. Clients must treat it as an opaque token and only ever echo it back verbatim.
- **`v: 1`** — the sort key is baked into the token. If sort order ever changes, old in-flight cursors must be rejected rather than silently misinterpreted. The decoder accepts `v == 1` only.

**Float precision is a correctness requirement, not a formatting preference.** Serialize `created_at` with the JSON library's default float handling (Python's `json` uses `repr`, which round-trips a double exactly). Do **not** format it as `"%.6f"`, do not round it, do not stringify it. The predicate in §2 contains `created_at = :c_created_at`; any lost precision makes that equality never match, which silently breaks the tie-break branch and reintroduces skipped rows in exactly the 120-row case above.

**Decoding — reject with `400` if any check fails:**
1. Re-pad and base64url-decode. Failure → invalid.
2. `json.loads`. Failure, or result is not a JSON object → invalid.
3. `v` present and `== 1` → else invalid.
4. `created_at` present and is a JSON number (`int` or `float`; reject `bool`) → else invalid.
5. `id` present and is an integer (reject `bool`) → else invalid.

Response: `400` with body `{"detail": "invalid cursor"}`. Do **not** use `422` (that's FastAPI's own validation shape and would conflate a malformed token with a schema violation), and do **not** silently fall back to page 1 — that turns a client bug into an infinite pagination loop.

**Filters are not encoded in the cursor.** The caller re-sends `q`/`status`/`min_priority`/`max_priority` alongside `cursor` on every request. This matches the tests, which resend `limit` and `cursor` only. The alternative — embedding the filter set in the token and rejecting mismatches — is rejected as unnecessary for this spec. Document in the docstring that changing filters while holding a cursor yields undefined-but-safe results.

---

## 4. Query parameters

| Param | Type | Default | Validation | Notes |
|---|---|---|---|---|
| `q` | `str \| None` | `None` | none | substring match on `title` |
| `status` | `str \| None` | `None` | **no enum** | exact match; tests use `open`/`done` but do not constrain the domain |
| `min_priority` | `int \| None` | `None` | none | inclusive |
| `max_priority` | `int \| None` | `None` | none | inclusive |
| `cursor` | `str \| None` | `None` | see §3 | opaque |
| `limit` | `int` | `20` | **see trap below** | clamped to `[1, 100]` |

### The `limit` trap — read this before writing the signature

`test_search_limit_capped_at_100` sends `limit=500` and asserts **`status_code == 200`**. If you declare `limit: int = Query(20, ge=1, le=100)`, FastAPI rejects with **422** and the test fails. The cap is a **silent clamp, not a validation constraint.**

Declare `limit` with **no `le` and no `ge`**, and clamp in the handler: values above `100` become `100`, values below `1` become `1`. The endpoint must never return `422` for any integer `limit`. A non-integer `limit` still 422s via FastAPI's normal coercion; that is acceptable and untested.

Other semantics, decided so the implementer doesn't have to:
- `min_priority > max_priority` → no special case; the query naturally returns `[]` with `200`.
- `q=None` → no `q` clause at all. `q=""` → clause is added and matches everything (`LIKE '%%'`); harmless, no special-casing.
- Unknown extra query params → ignored (FastAPI default).

---

## 5. SQL construction

Build a `list` of WHERE fragment strings and a parallel `list` of bound parameters, appending in the order below, then join fragments with `" AND "`. **Every** user-supplied value is a `?` placeholder. No value is ever interpolated into the SQL string; the only dynamically-assembled text is the fixed fragments below.

**Select list** — enumerate columns explicitly rather than `SELECT *`, so the row shape is pinned:

```sql
SELECT id, title, description, status, priority, created_at FROM tasks
```

**Fragments, in this append order:**

| Condition | Fragment | Params appended |
|---|---|---|
| `q is not None` | `title LIKE ? ESCAPE '\'` | `"%" + escape_like(q) + "%"` |
| `status is not None` | `status = ?` | `status` |
| `min_priority is not None` | `priority >= ?` | `min_priority` |
| `max_priority is not None` | `priority <= ?` | `max_priority` |
| `cursor is not None` | `(created_at < ? OR (created_at = ? AND id < ?))` | `c_created_at`, `c_created_at`, `c_id` |

If the fragment list is empty, omit the `WHERE` keyword entirely (or use `WHERE 1=1` as the seed — either is fine, pick one and be consistent).

**`escape_like(s)`** — replace, **in this order**: `\` → `\\`, then `%` → `\%`, then `_` → `\_`. Backslash first, or you double-escape the escapes. This is required: the probe confirmed that an unescaped `_` in `q` acts as a single-character wildcard, so a search for `rep_ort` would match `report`. Note that `'\'` inside the SQL text is a literal backslash in a SQL string literal — in Python source this means the SQL fragment must be a raw string or use `'\\'`.

**No `LOWER()` on either side.** SQLite's default `LIKE` is already ASCII-case-insensitive (verified), which satisfies "case-insensitive substring match" for the tested inputs. Adding `LOWER()` buys nothing — SQLite's `LOWER()` is ASCII-only too, so it does not extend coverage to non-ASCII — while defeating any future index on `title`. Document the known limitation: non-ASCII characters are matched case-**sensitively**. Fixing that requires the ICU extension and is out of scope.

**Tail:**

```sql
ORDER BY created_at DESC, id DESC
LIMIT ?
```

with the final bound parameter being **`effective_limit + 1`** (see §6).

**Full shape of the worst case** (all filters + cursor), for reference:

```sql
SELECT id, title, description, status, priority, created_at
FROM tasks
WHERE title LIKE ? ESCAPE '\'
  AND status = ?
  AND priority >= ?
  AND priority <= ?
  AND (created_at < ? OR (created_at = ? AND id < ?))
ORDER BY created_at DESC, id DESC
LIMIT ?
```

Bound parameters, in order: `%q%`, `status`, `min_priority`, `max_priority`, `c_created_at`, `c_created_at`, `c_id`, `effective_limit + 1`.

---

## 6. The `limit + 1` fetch, and computing `next_cursor`

Query for `effective_limit + 1` rows. Then:

- If `len(rows) > effective_limit`: there is at least one more page. **Discard the extra row**, keep the first `effective_limit`, and set `next_cursor = encode(created_at, id)` **of the last kept row** (not the discarded probe row).
- Otherwise: `next_cursor = None`.

Do **not** instead set `next_cursor` whenever `len(rows) == effective_limit`. That emits a non-null cursor on a final page that happens to fit exactly, forcing every client into one guaranteed-empty extra round trip. Both approaches pass the given tests; only this one is correct.

---

## 7. Response schema

`200 OK`, `Content-Type: application/json`, exactly these three top-level keys:

```json
{
  "results": [
    {
      "id": 5,
      "title": "Original 4",
      "description": "",
      "status": "open",
      "priority": 3,
      "created_at": 1725441234.567891
    }
  ],
  "next_cursor": "eyJ2IjoxLCJjcmVhdGVkX2F0IjoxNzI1NDQxMjM0LjU2Nzg5MSwiaWQiOjR9",
  "limit": 2
}
```

- **`results`** — JSON array, ordered newest-first, length `0 <= n <= limit`. Each element must be **byte-identical in shape** to what `row_to_dict` (`main.py:27`) already returns for `GET /tasks/{id}` and `GET /tasks`: keys `id`, `title`, `description`, `status`, `priority`, `created_at`, in that order. Reuse `row_to_dict`; do not hand-roll a second serializer that can drift.
- **`next_cursor`** — opaque `string`, or `null` when this is the last page. Never omitted, never `""`.
- **`limit`** — integer, the **effective** limit after clamping. So `?limit=500` responds with `"limit": 100`. This makes the silent clamp observable to clients instead of mysterious.

**Deliberately excluded: `total` / `count`.** A total requires a second `COUNT(*)` query, and its value is stale the instant it's computed — it is unstable under concurrent writes for precisely the reason offsets are. Do not add it.

Error response, malformed cursor only: `400` with `{"detail": "invalid cursor"}`.

---

## 8. Placement in `main.py` and connection handling

1. **Insert the new route handler above `get_task` at `main.py:51`.** This is non-negotiable and is the single highest-risk detail in this document: appending it at the bottom of the file (where the spec comment sits) makes every test fail with `422`, verified above. Leave a short comment at the insertion point explaining that static path segments must precede `/tasks/{task_id}`, so nobody "tidies up" the file later and silently breaks it.
2. **Decode and validate the cursor before opening the database connection.** The `400` path then cannot leak a connection. (The existing handlers do leak on some error paths — don't copy that; don't fix it in this change either.)
3. Otherwise follow the established pattern exactly: `get_conn()`, `conn.execute(sql, params).fetchall()`, `conn.close()`, return the dict. Read-only, so no `commit()`. Close the connection on the success path before serializing.
4. Response model: returning a plain `dict` is consistent with the existing handlers. A Pydantic response model is optional and must not change the wire shape in §7 if added.

---

## 9. Worked trace of the acceptance test (use this to debug)

Rows: ids 1–5 with ascending `created_at`; `ca_n` = `created_at` of id `n`.

| Step | Request | SQL effect | Result |
|---|---|---|---|
| Page 1 | `limit=2`, no cursor | no WHERE, `ORDER BY created_at DESC, id DESC`, `LIMIT 3` | fetched `[5,4,3]`; `3 > 2` → drop `3`; `results=[5,4]`; `next_cursor = enc(ca_4, 4)` |
| Concurrent insert | `POST /tasks` | id 6, `created_at > ca_5` | table now 6 rows |
| Page 2 | `limit=2`, `cursor` | `WHERE (created_at < ca_4 OR (created_at = ca_4 AND id < 4))`, `LIMIT 3` | id 6 excluded (`ca_6 > ca_4`); ids 5,4 excluded; fetched `[3,2,1]`; `3 > 2` → drop `1`; `results=[3,2]`; `next_cursor = enc(ca_2, 2)` |

`page2_ids == [original[2].id, original[1].id] == [3, 2]` — assertion at line 93 satisfied. An `OFFSET 2` implementation returns `[4, 3]` here.

Expected outcome: all 6 tests in `tests/test_search.py` pass, all 5 in `tests/test_crud.py` continue to pass (regression check on the route-ordering change).

---

## 10. Optional, out of scope for the tests

A covering index would make the keyset predicate an index range scan instead of a full table scan:

```sql
CREATE INDEX IF NOT EXISTS idx_tasks_created_at_id ON tasks (created_at DESC, id DESC);
```

The tests do not need it and it is not required for correctness. Mention it in a comment or add it to `init_db` only if the reviewer wants it; keyset pagination's `O(log n)` seek advantage over `OFFSET` is unrealized without it.

---

Two things I'd flag for your call before someone implements this:

1. **`limit` clamping vs. rejecting.** I specified a silent clamp because `test_search_limit_capped_at_100` asserts `200`. That's forced by the test, but silent clamping is arguably a worse API than `422`. I surfaced it via the `limit` field in the response. Fine, or do you want a warning header?
2. **The index in §10.** Adding it touches `init_db`, which is shared with the CRUD tests. I left it out to keep the diff to `main.py` only. Say the word if you'd rather it be included.