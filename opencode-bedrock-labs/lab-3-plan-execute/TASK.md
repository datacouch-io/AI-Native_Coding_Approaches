# Task: a data export module

Build `exporter.py`, a module that turns a list of record dicts into CSV or JSON,
with optional filtering.

## Required public API

```python
class ExportError(ValueError): ...

def to_csv(rows: list[dict], fields: list[str]) -> str: ...
def to_json(rows: list[dict], fields: list[str]) -> str: ...
def filter_rows(rows: list[dict], where: dict) -> list[dict]: ...
def export(rows: list[dict], *, fmt: str, fields: list[str],
           where: dict | None = None, path: str | None = None) -> str: ...
```

Field names may use dotted paths to read nested values: `"user.name"` reads
`row["user"]["name"]`. A missing path yields an empty value, never an exception.

## Acceptance milestones

The work is graded in four milestones. Each has a fixed acceptance test class in
`tests/test_acceptance.py`. A milestone is done when its class passes AND every
earlier milestone still passes.

**M1 - to_csv**
- First line is the header: the `fields` list, comma separated, in order.
- RFC4180 quoting: values containing a comma, double quote, CR or LF are wrapped
  in double quotes, and inner double quotes are doubled.
- `None` and missing values render as an empty field.
- Lines are joined with `\r\n` and the output ends with a trailing `\r\n`.
- Dotted field paths resolve into nested dicts.

**M2 - to_json**
- Returns a JSON array of objects, one per row.
- Each object contains exactly the requested `fields`, as keys, in the order given.
- Missing or unreachable paths yield `null`.
- Values keep their original JSON types - numbers stay numbers, booleans stay booleans.

**M3 - filter_rows**
- `where` maps a field path to an expected value; all conditions must match (AND).
- Suffix operators: `field__gt`, `field__gte`, `field__lt`, `field__lte`,
  `field__in` (value is a list), `field__contains` (case-sensitive substring).
- A bare `field` means equality.
- An unknown suffix operator raises `ExportError`.
- Comparing incompatible types excludes the row rather than raising.

**M4 - export**
- `fmt` must be `"csv"` or `"json"`; anything else raises `ExportError`.
- `where` is applied before formatting; `None` means no filtering.
- With `path=None`, returns the formatted string.
- With a `path`, writes UTF-8 to that path and returns the path.
- An empty `fields` list raises `ExportError`.
