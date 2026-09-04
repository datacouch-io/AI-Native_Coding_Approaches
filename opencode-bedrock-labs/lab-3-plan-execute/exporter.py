"""
exporter.py - Data export module.

Turns a list of record dicts into CSV or JSON, with optional filtering.
Stdlib-only: csv, io, json.
"""

import csv
import io
import json


class ExportError(ValueError):
    """Raised when export arguments or filter conditions are invalid."""
    ...


# Unique sentinel meaning "this path does not exist". Never confuse with None,
# which means "the path exists and its stored value is null".
_MISSING = object()


def _get_path(row, path):
    """Resolve a dotted path against a dict. Returns _MISSING if unreachable.

    Never raises - an intermediate value that isn't a dict simply yields
    _MISSING rather than a TypeError/KeyError/AttributeError.
    """
    current = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _csv_cell(value):
    """Convert a resolved value into the string to write into a CSV cell.

    _MISSING and None both render as an empty field. Everything else is
    stringified as-is; quoting/escaping is handled separately.
    """
    if value is _MISSING or value is None:
        return ""
    return str(value)


def _csv_quote(cell: str) -> str:
    """RFC4180-minimal-quote a single already-stringified cell.

    Quote only if the cell contains a comma, double quote, CR or LF; inner
    double quotes are doubled. This intentionally does NOT go through
    csv.writer, because csv.writer quotes a lone empty-string field in a
    single-column row (to disambiguate it from a blank line) - a quirk that
    would incorrectly quote a missing/empty value when there's only one
    field, which is not the behaviour this module specifies.
    """
    if any(ch in cell for ch in (",", '"', "\r", "\n")):
        return '"' + cell.replace('"', '""') + '"'
    return cell


def to_csv(rows: list[dict], fields: list[str]) -> str:
    lines = [",".join(_csv_quote(f) for f in fields)]
    for row in rows:
        cells = [_csv_cell(_get_path(row, f)) for f in fields]
        lines.append(",".join(_csv_quote(c) for c in cells))
    return "\r\n".join(lines) + "\r\n"


def to_json(rows: list[dict], fields: list[str]) -> str:
    """Return a JSON array of flat objects, one per row.

    Each object has exactly the requested `fields` as keys, in the given
    order, with values taken verbatim from `_get_path` (original JSON
    types preserved - no stringification). A missing/unreachable path
    serialises as `null`; a stored `None` also serialises as `null`.
    """
    objects = []
    for row in rows:
        obj = {}
        for f in fields:
            v = _get_path(row, f)
            obj[f] = None if v is _MISSING else v
        objects.append(obj)
    return json.dumps(objects, ensure_ascii=False)


# Known suffix operators for `where` keys (everything except bare equality).
_COMPARISON_OPS = {"gt", "gte", "lt", "lte", "in", "contains"}


def _parse_key(key):
    """Parse a `where` key into (path, operator).

    A key with no "__" is a bare-equality path with operator "eq". Otherwise
    split at the LAST "__" into (path, suffix); if `suffix` is not a known
    operator, raise ExportError - including empty/garbage suffixes such as
    "score__" or "score__wat". A field whose own name legitimately contains
    "__" therefore cannot be filtered as bare equality; no heuristic rescues
    that case.
    """
    if "__" not in key:
        return key, "eq"
    path, _, suffix = key.rpartition("__")
    if suffix not in _COMPARISON_OPS:
        raise ExportError(f"Unknown filter operator suffix {suffix!r} in key {key!r}")
    return path, suffix


def _match(row, path, op, expected) -> bool:
    """Evaluate a single parsed condition against one row.

    A missing/unreachable path excludes the row for every operator,
    equality included. A comparison that raises TypeError (incompatible
    types) excludes the row rather than propagating - callers must only
    call this after `_parse_key` has already validated the operator, so no
    ExportError needs to (or should) be caught here.
    """
    actual = _get_path(row, path)
    if actual is _MISSING:
        return False
    try:
        if op == "eq":
            return actual == expected
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
        if op == "in":
            return actual in expected
        if op == "contains":
            # Case-sensitive substring check: is `expected` contained in
            # the row's actual value? (direction matters - not the reverse.)
            return expected in actual
    except TypeError:
        return False
    # Unreachable: _parse_key already restricts `op` to a known value.
    return False


def filter_rows(rows: list[dict], where: dict) -> list[dict]:
    """Return the rows matching every condition in `where` (AND semantics).

    Every key in `where` is parsed - and thus validated - up front, before
    any filtering happens. This guarantees an unknown suffix operator always
    raises ExportError, even for an empty `rows` list and even if `all()`
    would have short-circuited past it during evaluation.
    """
    conditions = [(*_parse_key(key), expected) for key, expected in where.items()]
    return [
        row
        for row in rows
        if all(_match(row, path, op, expected) for path, op, expected in conditions)
    ]


def export(rows: list[dict], *, fmt: str, fields: list[str],
           where: dict | None = None, path: str | None = None) -> str:
    """Filter and format `rows`, returning a string or a written file path.

    Validation happens first, before any filtering or formatting work:
    `fmt` must be exactly "csv" or "json", and `fields` must be a non-empty
    list. Both checks raise ExportError, independent of each other - the
    empty-fields check fires even when `fmt` is valid.

    Filtering (via `filter_rows`) happens before formatting, so the output
    only reflects matching rows. `where=None` (or an empty dict) means no
    filtering.

    If `path` is None, the formatted string is returned. Otherwise it is
    written to `path` as UTF-8 with `newline=""` (so the CSV format's own
    "\\r\\n" line endings are written literally rather than being translated),
    and `path` is returned unchanged.
    """
    if fmt not in ("csv", "json"):
        raise ExportError(f"Unsupported export format {fmt!r}; expected 'csv' or 'json'")
    if not fields:
        raise ExportError("`fields` must be a non-empty list")

    filtered = filter_rows(rows, where) if where else list(rows)

    if fmt == "csv":
        formatted = to_csv(filtered, fields)
    else:
        formatted = to_json(filtered, fields)

    if path is None:
        return formatted

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(formatted)
    return path
