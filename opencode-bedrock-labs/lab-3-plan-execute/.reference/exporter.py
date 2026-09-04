"""Reference solution - used only to prove the acceptance suite is satisfiable."""
import io
import json
from typing import Any

_MISSING = object()
_OPS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: isinstance(a, str) and b in a,
}


class ExportError(ValueError):
    pass


def _resolve(row: dict, path: str) -> Any:
    cur: Any = row
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _csv_cell(value: Any) -> str:
    if value is _MISSING or value is None:
        return ""
    text = str(value)
    if any(c in text for c in (",", '"', "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def to_csv(rows: list[dict], fields: list[str]) -> str:
    out = io.StringIO()
    out.write(",".join(_csv_cell(f) for f in fields))
    out.write("\r\n")
    for row in rows:
        out.write(",".join(_csv_cell(_resolve(row, f)) for f in fields))
        out.write("\r\n")
    return out.getvalue()


def to_json(rows: list[dict], fields: list[str]) -> str:
    payload = []
    for row in rows:
        obj = {}
        for f in fields:
            v = _resolve(row, f)
            obj[f] = None if v is _MISSING else v
        payload.append(obj)
    return json.dumps(payload)


def filter_rows(rows: list[dict], where: dict) -> list[dict]:
    if not where:
        return list(rows)
    parsed = []
    for key, expected in where.items():
        path, _, suffix = key.rpartition("__")
        if not path:
            parsed.append((key, None, expected))
        elif suffix in _OPS:
            parsed.append((path, suffix, expected))
        else:
            raise ExportError(f"unknown operator in {key!r}")

    kept = []
    for row in rows:
        ok = True
        for path, op, expected in parsed:
            actual = _resolve(row, path)
            if actual is _MISSING:
                ok = False
                break
            if op is None:
                if actual != expected:
                    ok = False
                    break
            else:
                try:
                    if not _OPS[op](actual, expected):
                        ok = False
                        break
                except TypeError:
                    ok = False
                    break
        if ok:
            kept.append(row)
    return kept


def export(rows: list[dict], *, fmt: str, fields: list[str],
           where: dict | None = None, path: str | None = None) -> str:
    if not fields:
        raise ExportError("fields must not be empty")
    if fmt not in ("csv", "json"):
        raise ExportError(f"unsupported format {fmt!r}")
    selected = filter_rows(rows, where or {})
    text = to_csv(selected, fields) if fmt == "csv" else to_json(selected, fields)
    if path is None:
        return text
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path
