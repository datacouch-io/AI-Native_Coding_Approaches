I'll inspect the sandbox to see what already exists before writing the plan.# Build Plan — `exporter.py`

A single stdlib-only module (`csv`, `io`, `json`). No third-party imports, no CLI, no I/O at import time. Target Python 3.10+ (`dict | None` in signatures is fine).

---

## 0. Global invariants — read before every milestone

These apply to **all four** milestones. Violating any of them fails the gate even if your milestone's own logic is right.

### 0.1 THE FILE MUST ALWAYS EXPORT ALL FIVE PUBLIC NAMES

The acceptance suite imports every public name **at module import time**, in one statement, for *every* milestone run:

```python
from exporter import ExportError, export, filter_rows, to_csv, to_json
```

So from **M1 onward**, `exporter.py` must define, at module level:

`ExportError`, `to_csv`, `to_json`, `filter_rows`, `export`

If a function is not yet implemented in your current milestone, define it as a stub with the **final signature** and a body of `raise NotImplementedError`. A stub raising when *called* is fine; a *missing name* makes the import fail and every test — including the ones you just wrote — errors out.

Do **not** delete or rename anything in a later milestone. Each milestone only replaces the body of its own stub.

### 0.2 Signatures are frozen — copy them exactly

```python
class ExportError(ValueError): ...

def to_csv(rows: list[dict], fields: list[str]) -> str: ...
def to_json(rows: list[dict], fields: list[str]) -> str: ...
def filter_rows(rows: list[dict], where: dict) -> list[dict]: ...
def export(rows: list[dict], *, fmt: str, fields: list[str],
           where: dict | None = None, path: str | None = None) -> str: ...
```

`ExportError` subclasses `ValueError` (not `Exception`). Note the `*` in `export`: `fmt`, `fields`, `where`, `path` are **keyword-only**. Add no extra parameters, and give none of `rows`/`fields` a default.

### 0.3 The shared helper: `_MISSING` + `_get_path`

Build this in M1. M2, M3 and M4 all depend on it. Do not write a second path resolver later.

```python
_MISSING = object()   # module-level unique sentinel

def _get_path(row, path):
    """Resolve a dotted path. Returns _MISSING if unreachable. Never raises."""
    current = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current
```

Rules this encodes — all deliberate:

- A field with no dot (`"name"`) uses the same code path; `"name".split(".")` is `["name"]`.
- Always split on `"."`. Do **not** add a fallback that looks up the literal dotted string as a single key.
- If an intermediate value is not a dict (e.g. `row["user"]` is a string or a list), the result is `_MISSING`, not an exception. Never let `TypeError`/`KeyError`/`AttributeError` escape.
- **`_MISSING` is not `None`.** `_MISSING` means *"this path does not exist"*. `None` means *"the path exists and its stored value is null"*. Test with `is`/`is not`, never `==`, and never with a truthiness check (`0`, `""`, `False` and `None` are all falsy but all real values).
- Why the distinction matters even though M1/M2 render both the same way: M3's filtering must treat "no value here" as *never matching any condition*, while a stored `None` is a real value that can legitimately equal `None`. Collapsing the sentinel into `None` in M1 destroys information M3 needs.
- `_get_path` returns the value **unconverted**. String conversion is M1's job; JSON typing is M2's job. Do not stringify inside the helper.

---

## M1 — `to_csv`

### 1. Goal
`exporter.py` exists with `ExportError`, the `_MISSING`/`_get_path` helper, a working `to_csv`, and `NotImplementedError` stubs for `to_json`, `filter_rows`, `export`.

### 2. Design decisions

- **Use the `csv` module**, configured explicitly, rather than hand-rolling quoting:
  ```python
  buffer = io.StringIO(newline="")
  writer = csv.writer(buffer, delimiter=",", quotechar='"', doublequote=True,
                      escapechar=None, quoting=csv.QUOTE_MINIMAL,
                      lineterminator="\r\n")
  ```
  `QUOTE_MINIMAL` is mandatory. `QUOTE_ALL` quotes plain values and fails the suite.
  `newline=""` on the `StringIO` prevents newline translation of embedded `\n`.
- **Cell conversion helper** — add `_csv_cell(value)`:
  - `value is _MISSING` or `value is None` → `""`
  - otherwise → `str(value)`
  Do not pass raw objects to `writer.writerow` and hope; and do not use `str(None)`, which yields the literal `"None"`.
- **Header row** is the `fields` list written through the same writer, verbatim. `"user.name"` appears in the header as `user.name` — it is not split, prettified, or quoted (it needs no quoting).
- **Output shape**: every row, header included, is terminated by `\r\n`, so the string *ends* with `\r\n`. "Joined with `\r\n` plus a trailing `\r\n`" is the same thing as "`\r\n` after each line". `buffer.getvalue()` with `lineterminator="\r\n"` already produces exactly this — do not `strip()`, `rstrip()`, or `join()` afterwards.

### 3. Implementation notes

Order in the file: imports → `ExportError` → `_MISSING` → `_get_path` → `_csv_cell` → `to_csv` → stubs.

`to_csv`: create buffer/writer, `writer.writerow(list(fields))`, then for each row `writer.writerow([_csv_cell(_get_path(row, f)) for f in fields])`, then `return buffer.getvalue()`. Empty `rows` → header line only (no crash). Empty `fields` → do not crash here; `export` is the layer that rejects it in M4.

### 4. Self-check

Confirm these exact strings (byte for byte, including `\r`):

- `to_csv([{"name": "Ada"}], ["name"])` → `'name\r\nAda\r\n'` — one `\r\n` after the header, one after the row, nothing more, and `Ada` is **unquoted**.
- `to_csv([{"note": 'say "hi", then go'}], ["note"])` → `'note\r\n"say ""hi"", then go"\r\n'`
- `to_csv([{"note": "line1\nline2"}], ["note"])` → `'note\r\n"line1\nline2"\r\n'` — **the embedded newline stays a bare `\n`.** It is quoted but not converted to `\r\n`.
- `to_csv([{"a": None}], ["a", "absent"])` → `'a,absent\r\n,\r\n'`
- `to_csv([{"user": {"name": "x"}}], ["user.name"])` → `'user.name\r\nx\r\n'`
- `to_csv([{"user": {}}], ["user.name"])` → `'user.name\r\n\r\n'` (no exception)
- Finally: `import exporter` succeeds and `exporter.to_json`, `exporter.filter_rows`, `exporter.export`, `exporter.ExportError` all resolve.

---

## M2 — `to_json`

### 1. Goal
`to_json` returns a JSON **string** encoding an array of one flat object per row, keyed by the requested field paths in order.

### 2. Reuses from M1
`_get_path` and `_MISSING` — unchanged. Do not touch `to_csv`, `_csv_cell`, or `ExportError`.

### 3. Design decisions

- **Keys are the field strings verbatim.** `fields=["user.name"]` produces `{"user.name": "ada@example.com"}` — a flat key containing a dot. Do **not** rebuild nested structure (`{"user": {"name": ...}}`).
- **Exactly the requested fields**, nothing else. Never merge or fall back to the original row's keys.
- **Key order = `fields` order.** Build a plain `dict` by inserting in `fields` order (dicts preserve insertion order) and call `json.dumps(..., ensure_ascii=False)` with **`sort_keys` left at its default `False`**. Passing `sort_keys=True` fails the ordering test.
- **`_MISSING` → `None`** (serialised as `null`). A real `None` also serialises as `null`. Both map to null here; the sentinel still matters for M3.
- **No stringification.** `91.5` must stay the number `91.5`, `True` must stay the boolean `true`, `1` must stay `1`. Let `json.dumps` handle the types; do not call `str()`, and do not pass `default=str`.
- Return type is `str`. Do not return the list.

### 4. Implementation notes

Replace the `to_json` stub only:

```
objects = []
for row in rows:
    obj = {}
    for f in fields:
        v = _get_path(row, f)
        obj[f] = None if v is _MISSING else v
    objects.append(obj)
return json.dumps(objects, ensure_ascii=False)
```

Indentation/separators are free (the grader parses the string), but keep it simple and unindented.

### 5. Self-check

- `json.loads(to_json([{"id": 1, "name": "Ada"}], ["id", "name"]))` → `[{"id": 1, "name": "Ada"}]`
- `list(json.loads(to_json([{"id": 1, "name": "Ada"}], ["name", "id"]))[0].keys())` → `["name", "id"]`
- `json.loads(to_json([{"score": 91.5, "active": True}], ["score", "active"]))[0]["active"] is True` → `True` (i.e. it is a bool, not `"True"`)
- `json.loads(to_json([{"user": {}}], ["user.name"]))[0]["user.name"] is None` → `True`
- Re-verify all M1 self-checks still hold.

---

## M3 — `filter_rows`

### 1. Goal
`filter_rows` returns a new list of the rows satisfying every condition in `where`, preserving input order, raising `ExportError` on an unknown suffix operator and silently excluding rows on type-incompatible comparisons.

### 2. Reuses from M1/M2
`_get_path`, `_MISSING`, `ExportError`. Do not modify `to_csv` or `to_json`.

### 3. Design decisions

- **Key parsing.** For each key in `where`:
  - If `"__"` is **not** in the key → operator is equality, path is the whole key.
  - If `"__"` **is** in the key → `path, _, suffix = key.rpartition("__")`; split at the **last** `"__"`. If `suffix` is in the known operator set, use it. **If it is not, raise `ExportError`** — including empty/garbage suffixes like `"score__"` or `"score__wat"`. Consequence, and it is intended: a real field whose name contains `"__"` cannot be filtered as a bare equality. Do not add heuristics to "rescue" it.
  - Raise on an unknown operator **regardless of whether any row would have matched** — i.e. validate the key while evaluating, and let the exception propagate even if `rows` is empty.
- **Operator set** (exactly these six behaviours):

  | key form | semantics |
  |---|---|
  | `field` | `actual == expected` |
  | `field__gt` | `actual > expected` |
  | `field__gte` | `actual >= expected` |
  | `field__lt` | `actual < expected` |
  | `field__lte` | `actual <= expected` |
  | `field__in` | `actual in expected` (expected is a list) |
  | `field__contains` | case-**sensitive** substring: `expected in actual` for strings |

- **`__contains` direction matters**: it asks whether the *expected* value is a substring of the row's *actual* value (`expected in actual`). Getting this backwards passes some cases by accident and fails others.
- **`__contains` must not be case-folded.** No `.lower()`, no `casefold()`. `"CLEAN"` must not match `"clean"`.
- **Missing path (`_MISSING`) excludes the row** for every operator, including bare equality. Check `if actual is _MISSING: return False` before comparing.
- **Type errors exclude, never raise.** Wrap each comparison in `try: ... except TypeError: return False`. `"Ada" > 5` raises `TypeError` in Python — it must yield "no match", not a traceback. Apply the same guard to `__in` and `__contains` (e.g. `actual` is not a string, or `expected` is not iterable) — catch `TypeError` there too.
- **`ExportError` from an unknown operator must not be swallowed** by those `try/except` blocks. Raise it *outside* / *before* the comparison `try`, or catch only `TypeError` (never bare `except:` or `except Exception`).
- **Equality uses `==`**, not `is`. Note Python quirk: `True == 1` and `False == 0`. This is acceptable and does not need special-casing.
- **AND semantics**: a row is kept only if all conditions hold. `where == {}` → all rows kept.
- **Return a `list`, not a generator or filter object** — callers compare it with `== []` and take `len()`. The list must contain the **original row dict objects** (same identity, no copies, no field projection) in their original order. Do not mutate `rows` or any row.

### 4. Implementation notes

Add a private predicate and keep `filter_rows` thin:

```
def _match(row, key, expected) -> bool     # resolves path, dispatches operator
def filter_rows(rows, where):
    return [r for r in rows if all(_match(r, k, v) for k, v in where.items())]
```

Caveat with that one-liner: `all(...)` short-circuits, so an unknown operator later in `where` might never be evaluated if an earlier condition fails. To guarantee `ExportError` is always raised, **validate every key in `where` first** — a small loop over `where` that parses each key and raises `ExportError` on an unknown suffix — then do the filtering pass. Consider factoring the parse into `_parse_key(key) -> (path, op)` used by both the validation loop and `_match`.

### 5. Self-check

Using rows `[{"id":1,"name":"Ada","score":91.5,"active":True,"user":{"name":"a@x"},"note":"clean"}, {"id":2,"name":"Grace","score":78.0,"active":False,"user":{"name":"g@x"},"note":'say "hi"'}, {"id":3,"name":"Linus","score":64.25,"active":True,"user":{},"note":"line1\nline2"}]`:

- `{"active": True}` → ids `[1, 3]`
- `{"active": True, "name": "Ada"}` → ids `[1]`
- `{"score__gt": 78.0}` → `[1]`; `{"score__gte": 78.0}` → `[1, 2]`; `{"score__lt": 78.0}` → `[3]`; `{"score__lte": 78.0}` → `[2, 3]`
- `{"name__in": ["Ada", "Linus"]}` → `[1, 3]`
- `{"note__contains": "clean"}` → `[1]`; `{"note__contains": "CLEAN"}` → `[]`
- `{"user.name": "g@x"}` → `[2]`
- `{"score__wat": 1}` → raises `ExportError` (and `ExportError` is caught by `except ValueError`)
- `{"name__gt": 5}` → `[]` with **no exception**
- `{}` → all 3 rows
- Re-verify all M1 and M2 self-checks still hold.

---

## M4 — `export`

### 1. Goal
`export` validates its arguments, optionally filters, formats as CSV or JSON, and either returns the formatted string or writes it to `path` as UTF-8 and returns `path`.

### 2. Reuses from M1–M3
`to_csv`, `to_json`, `filter_rows`, `ExportError` — call them, do not reimplement or inline their logic. `export` contains no path resolution, no quoting and no comparison code of its own.

### 3. Design decisions

- **Order of operations**, exactly: validate → filter → format → write-or-return.
- **Validation first, before any work:**
  - `fmt` must be exactly `"csv"` or `"json"`. Anything else (including `"xml"`, `"CSV"`, `None`) → `raise ExportError(...)`. Do not normalise case; do not silently default.
  - `fields` must be a non-empty list. Empty (or `None`) → `raise ExportError(...)`. This check must fire **even when `fmt` is valid**, so it cannot live inside a format branch.
  - Raise `ExportError`, never `ValueError`/`KeyError`/`AssertionError` directly. (`ExportError` *is* a `ValueError`, so raising the subclass satisfies both.)
- **Filtering:** `rows = filter_rows(rows, where) if where else list(rows)`. `where=None` means no filtering. An empty dict `{}` also yields all rows, so the falsy check is safe. Filtering happens **before** formatting so the output only contains matching rows.
- **Formatting:** `"csv"` → `to_csv(rows, fields)`; `"json"` → `to_json(rows, fields)`.
- **Return contract:**
  - `path is None` → return the formatted string.
  - `path` given → write the string and return **`path` itself, unchanged** (the exact string passed in — do not `os.path.abspath`, `Path(...)`, resolve, or normalise it; the caller compares with `==`).
- **Writing:** `open(path, "w", encoding="utf-8", newline="")`. `newline=""` is required so the `\r\n` line endings already inside the CSV string are written literally instead of being translated (which would produce `\r\r\n` on Windows). Write the string once; add nothing (no extra trailing newline for JSON).
- `export` must not mutate `rows` or its dicts.

### 4. Implementation notes

Replace the `export` stub only. Keep the keyword-only `*` and the defaults `where=None, path=None`. Keep the module free of side effects — no `if __name__ == "__main__"` block is needed.

### 5. Self-check

- `export(rows, fmt="csv", fields=["name"])` → string whose first line is `name`
- `json.loads(export(rows, fmt="json", fields=["id"]))` → `[{"id":1},{"id":2},{"id":3}]`
- `export(rows, fmt="json", fields=["id"], where={"active": True})` → ids `[1, 3]`
- `export(rows, fmt="json", fields=["id"], where=None)` → 3 objects
- `export(rows, fmt="xml", fields=["id"])` → raises `ExportError`
- `export(rows, fmt="csv", fields=[])` → raises `ExportError`
- `export(rows, fmt="csv", fields=["name"], path="/tmp/out.csv")` → returns the string `"/tmp/out.csv"`, and that file read back with `encoding="utf-8"` has first line `name`
- Re-verify every M1, M2 and M3 self-check. **All four milestones are re-graded at this point.**

---

## Consolidated trap checklist

Tick each one before submitting any milestone.

1. **All five public names exist from M1 onward** (stubs for the unimplemented ones), or the test module's import fails and even the passing milestone scores zero.
2. `ExportError` subclasses `ValueError`.
3. Signatures unchanged; `export`'s args after `*` are keyword-only.
4. CSV uses `QUOTE_MINIMAL` — plain values are **not** quoted.
5. CSV ends with a trailing `\r\n`; nothing is stripped or re-joined.
6. An embedded `\n` inside a CSV value stays `\n` (quoted, not converted to `\r\n`).
7. `None` and missing render as an empty CSV field, never the text `None`.
8. JSON keys are the literal dotted field strings; no nested reconstruction.
9. JSON key order follows `fields`; `sort_keys` stays `False`.
10. JSON values keep their types — no `str()`, no `default=str`.
11. `to_json` returns a `str`, not a list.
12. `_get_path` never raises, including when an intermediate value is not a dict.
13. `_MISSING` is a unique sentinel compared with `is`, never `== None` and never via truthiness.
14. Operator suffix split at the **last** `"__"`; unknown suffix → `ExportError`, always raised (validate all `where` keys up front, since `all()` short-circuits).
15. `__contains` is `expected in actual`, case-sensitive.
16. Comparison `TypeError` → row excluded; catch **only** `TypeError` so `ExportError` still propagates.
17. Missing path excludes the row for every operator, equality included.
18. `filter_rows` returns a real `list` of the original row objects, in input order, unmutated.
19. `export` validates `fmt` **and** empty `fields` before doing anything else.
20. `export` filters before formatting.
21. `export` writes with `encoding="utf-8", newline=""` and returns the `path` string exactly as received.