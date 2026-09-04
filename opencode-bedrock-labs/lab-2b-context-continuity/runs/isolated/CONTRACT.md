Sandbox is empty (just `opencode.json`), Python 3.14. Here's the contract.

---

# API Contract: `expenses.py`

**Version:** 1.0 (frozen — implementers must not add, rename, or reorder public surface)
**Deliverables:** `expenses.py` (implementation), `test_expenses.py` (imports only from `expenses` + stdlib)
**Stdlib only.** No third-party dependencies. Target Python ≥ 3.11.

---

## 1. Module surface

```python
__all__ = [
    "ExpenseError",
    "RecordError",
    "DateRangeError",
    "MixedCurrencyError",
    "ValidatedExpense",
    "RejectedRecord",
    "ExpenseSummary",
    "MONEY_QUANTUM",
    "ROUNDING",
    "round_money",
    "validate_record",
    "summarize_expenses",
]
```

```python
from decimal import Decimal, ROUND_HALF_EVEN

MONEY_QUANTUM: Decimal = Decimal("0.01")
ROUNDING: str = ROUND_HALF_EVEN
```

Implementations MUST NOT mutate the global `decimal` context. All rounding goes through explicit `quantize(MONEY_QUANTUM, rounding=ROUNDING)`.

---

## 2. Input record shape

A record is a `Mapping[str, Any]` with exactly these four required keys:

| Key | Accepted types | Rules |
|---|---|---|
| `"date"` | `str` | MUST fully match `^\d{4}-\d{2}-\d{2}$` **and** be a real calendar date. |
| `"amount"` | `int`, `float`, `Decimal`, `str` | Finite, `>= 0`. `bool` is REJECTED. |
| `"category"` | `str` | Non-empty after `.strip()`. |
| `"currency"` | `str` | MUST fully match `^[A-Z]{3}$`. |

- Extra keys are ignored (no error).
- Missing keys are a rejection, not an exception.
- Date parsing MUST be the strict regex above followed by `datetime.date.fromisoformat`. Do **not** rely on `fromisoformat` alone: `"20240115"`, `"2024-1-5"`, and `"2024-01-15T10:00:00"` MUST all be rejected.

### 2.1 Amount coercion (exact, mandated)

```
int      -> Decimal(value)
Decimal  -> value            (as-is, unrounded)
float    -> Decimal(str(value))     # NEVER Decimal(float)
str      -> Decimal(value.strip())  # InvalidOperation -> rejection
```

`Decimal("NaN")`, `Decimal("Infinity")`, and `float("nan")/float("inf")` MUST be rejected as `"invalid_amount"` (check `is_finite()`).
`0` is a **valid** amount. `-0.0` is not `< 0` and is therefore **valid**.

### 2.2 Category normalization

Stored and grouped as `value.strip()`. **Case-sensitive**: `"Food"` and `"food"` are two distinct categories. No case folding, no title-casing.

### 2.3 Currency

No coercion. `"usd"` is a rejection, not `"USD"`.

---

## 3. Data types

All three are `@dataclass(frozen=True)`.

```python
@dataclass(frozen=True)
class ValidatedExpense:
    date: datetime.date
    amount: Decimal      # exact, UNROUNDED
    category: str        # stripped
    currency: str        # 3 uppercase letters
```

```python
@dataclass(frozen=True)
class RejectedRecord:
    index: int           # 0-based position in the input iterable
    record: Any          # the original object, unmodified
    reason: str          # one of the reason codes in §4.1
    field: str | None    # "date" | "amount" | "category" | "currency" | None
```

```python
@dataclass(frozen=True)
class ExpenseSummary:
    totals: dict[str, float]      # category -> rounded total; keys sorted ascending
    currency: str | None          # None iff accepted_count == 0
    grand_total: float            # 0.0 iff accepted_count == 0
    accepted_count: int
    filtered_out_count: int
    rejected: tuple[RejectedRecord, ...]   # input order
```

`totals` MUST be built so that iteration order is `sorted(categories)` (ascending, plain `str` ordering). A category whose exact sum quantizes to zero is still present with value `0.0`.

---

## 4. Exceptions

```python
class ExpenseError(Exception): ...

class RecordError(ExpenseError):
    def __init__(self, reason: str, field: str | None = None, index: int | None = None) -> None: ...
    reason: str
    field: str | None
    index: int | None

class DateRangeError(ExpenseError): ...

class MixedCurrencyError(ExpenseError):
    def __init__(self, currencies: Iterable[str]) -> None: ...
    currencies: tuple[str, ...]   # sorted ascending, deduplicated
```

Exception **message text is unspecified**. Tests MUST assert on the exception type and on the structured attributes (`.reason`, `.field`, `.index`, `.currencies`), never on `str(exc)`.

### 4.1 Reason codes (closed set)

`"not_a_mapping"`, `"missing_field"`, `"invalid_date"`, `"invalid_amount"`, `"negative_amount"`, `"invalid_category"`, `"invalid_currency"`

### 4.2 Validation precedence (mandated — a record with several faults yields exactly one reason)

1. Not a `collections.abc.Mapping` → `"not_a_mapping"`, `field=None`
2. Missing keys, checked in order `date`, `amount`, `category`, `currency` → `"missing_field"`, `field=` the first missing key
3. `date` invalid type/format/calendar → `"invalid_date"`, `field="date"`
4. `amount` wrong type / unparseable / non-finite / `bool` → `"invalid_amount"`, `field="amount"`
5. `amount < 0` → `"negative_amount"`, `field="amount"`
6. `category` not `str` or empty after strip → `"invalid_category"`, `field="category"`
7. `currency` not `str` or not `^[A-Z]{3}$` → `"invalid_currency"`, `field="currency"`

---

## 5. Functions

### 5.1 `round_money`

```python
def round_money(value: Decimal | int | float | str) -> Decimal: ...
```

- Coerces via §2.1, then `quantize(MONEY_QUANTUM, rounding=ROUNDING)`.
- Returns a `Decimal` with exactly 2 decimal places.
- Raises `ValueError` on unparseable/non-finite input. (This is the one place a bare `ValueError` is correct — it is a pure helper, not record validation.)
- Rejects `bool` with `TypeError`.

### 5.2 `validate_record`

```python
def validate_record(record: Any, index: int | None = None) -> ValidatedExpense: ...
```

- Applies §2 / §4.2. Raises `RecordError` with `.reason`, `.field`, and `.index` set from the argument.
- Returns `ValidatedExpense` with the **exact unrounded** amount. This function performs no rounding.
- `summarize_expenses` MUST delegate to this function; validation logic is not duplicated.

### 5.3 `summarize_expenses` (primary entry point)

```python
def summarize_expenses(
    records: Iterable[Mapping[str, Any]],
    *,
    start: str | datetime.date | None = None,
    end: str | datetime.date | None = None,
    strict: bool = False,
) -> ExpenseSummary: ...
```

`start` / `end` are **keyword-only**. `strict` is keyword-only.

#### Pipeline (mandated order)

1. **Range params.** Coerce `start`/`end`:
   - `None` → unbounded.
   - `datetime.date` → used as-is. A `datetime.datetime` MUST raise `DateRangeError` (note `datetime` is a subclass of `date`; check explicitly).
   - `str` → strict `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`; failure raises `DateRangeError`.
   - Any other type raises `DateRangeError`.
   - If both bounds present and `start > end` → `DateRangeError`.
2. **Input type.** If `records` is a `str`/`bytes`, or is not iterable → `TypeError`. A `Mapping` passed directly (a single record instead of a list) → `TypeError`.
3. **Per record**, enumerating from 0:
   - `validate_record(record, index)`.
   - On `RecordError`: if `strict` is `True`, re-raise immediately (with `.index` set); else append a `RejectedRecord` and continue.
   - On success: if `start` is set and `date < start`, or `end` is set and `date > end` → increment `filtered_out_count`, discard. Range is **inclusive** on both ends.
   - Otherwise accept.
4. **Currency check.** Collect the distinct currencies of **accepted** records only. If more than one → raise `MixedCurrencyError(currencies)`. Rejected records and range-filtered records never contribute to this check.
5. **Totals.** For each category, sum the **exact unrounded** `Decimal` amounts, then `quantize` once. Accumulators start at `Decimal("0")` (prevents `-0.00` leaking out).
6. **Grand total.** `grand_total = sum of the already-rounded per-category Decimal totals`, then quantize. This guarantees the invariant `grand_total == sum(rounded category totals)` exactly in `Decimal` space.
7. Convert every `Decimal` to `float` via `float(d)` for the returned dataclass.

#### Ordering notes

- `rejected` preserves input order.
- Validation happens **before** range filtering. Therefore a malformed record whose date is outside the range still appears in `rejected` (a malformed record has no trustworthy date, so it cannot be filtered).

#### Empty / all-rejected result

```python
ExpenseSummary(totals={}, currency=None, grand_total=0.0,
               accepted_count=0, filtered_out_count=<n>, rejected=(...))
```

No `MixedCurrencyError` is raised when zero records are accepted.

---

## 6. Rounding semantics (the highest-divergence area — read carefully)

Banker's rounding = round-half-to-even. Two mandates:

1. **Never use the builtin `round()` on floats for money.** `round(2.675, 2) == 2.67` because `2.675` is not exactly representable. The contract requires `2.68`.
2. **Sum exact, round once.** Per-category totals are the quantization of the exact sum, not the sum of individually-quantized amounts.

Required behaviour, exact values:

| Input | `round_money` result |
|---|---|
| `2.675` | `Decimal("2.68")` (tie → even digit 8) |
| `2.665` | `Decimal("2.66")` |
| `0.125` | `Decimal("0.12")` |
| `0.135` | `Decimal("0.14")` |
| `1.005` | `Decimal("1.00")` |
| `"1.014"` | `Decimal("1.01")` |
| `10` | `Decimal("10.00")` |

Sum-then-round discriminator: two `USD` records in category `"tips"` of `0.005` each → total `0.01`, **not** `0.00`.

---

## 7. Worked example (must pass verbatim)

```python
records = [
    {"date": "2024-01-05", "amount": 10.005, "category": "food",    "currency": "USD"},
    {"date": "2024-01-06", "amount": 10.005, "category": "food",    "currency": "USD"},
    {"date": "2024-01-07", "amount": "2.675", "category": "travel", "currency": "USD"},
    {"date": "2023-12-31", "amount": 99.0,   "category": "travel",  "currency": "USD"},
    {"date": "2024-01-08", "amount": -1.0,   "category": "food",    "currency": "USD"},
    {"date": "2024-13-01", "amount": 5.0,    "category": "food",    "currency": "USD"},
]

s = summarize_expenses(records, start="2024-01-01", end="2024-01-31")

s.totals             == {"food": 20.01, "travel": 2.68}   # keys sorted: food, travel
s.currency           == "USD"
s.grand_total        == 22.69
s.accepted_count     == 3
s.filtered_out_count == 1                                  # the 2023-12-31 record
[(r.index, r.reason, r.field) for r in s.rejected] == [
    (4, "negative_amount", "amount"),
    (5, "invalid_date",    "date"),
]
```

Note `food`: `10.005 + 10.005 = 20.01` exactly, then rounded → `20.01`. Rounding each first would give `20.00` (`10.00 + 10.00`) and is wrong.

---

## 8. Required tests for `test_expenses.py`

Plain `unittest` or `pytest`-style functions; the file must be runnable via `python -m pytest test_expenses.py` and must not require network access.

**Rounding:** every row of the §6 table; the `0.005 + 0.005` sum-then-round case; `round_money(True)` raises `TypeError`; `round_money("abc")` and `round_money(float("nan"))` raise `ValueError`.

**Validation (one test per reason code):** `not_a_mapping` (e.g. a list), `missing_field` for each of the four keys, `invalid_date` for `"2024-13-01"` / `"2024-1-5"` / `"20240115"` / `"2024-01-15T00:00:00"` / non-str, `invalid_amount` for `"abc"` / `None` / `True` / `float("inf")`, `negative_amount` for `-0.01`, `invalid_category` for `""` / `"   "` / non-str, `invalid_currency` for `"usd"` / `"US"` / `"USDD"` / `"US1"` / non-str.

**Precedence:** a record that is simultaneously bad-date and bad-currency yields `reason == "invalid_date"`; a record missing both `amount` and `currency` yields `field == "amount"`.

**Accepted edges:** `amount == 0` accepted; `amount == "1e2"` accepted as `100.00`; extra keys ignored; `category` `"  food  "` groups as `"food"`.

**Totals & grouping:** multi-category grouping; `totals` key order equals `sorted()`; case-sensitivity (`"Food"` and `"food"` stay separate); `grand_total` equals the sum of rounded category totals.

**Date range:** both bounds inclusive at the exact boundary dates; `start`-only; `end`-only; neither; range excluding everything → empty `totals`, `currency is None`, `grand_total == 0.0`; `filtered_out_count` correctness; `start > end` raises `DateRangeError`; malformed `start` string raises `DateRangeError`; `datetime.datetime` bound raises `DateRangeError`; `datetime.date` bound accepted.

**Mixed currency:** two accepted records with different currencies raise `MixedCurrencyError` with `.currencies == ("EUR", "USD")`; a *rejected* record with a different currency does **not** raise; a *range-filtered* record with a different currency does **not** raise; single currency across many records is fine.

**Strict mode:** `strict=True` raises `RecordError` on the first bad record with the correct `.index`, `.reason`, `.field`; `strict=True` with all-valid input returns the same `ExpenseSummary` as `strict=False`.

**Misc:** empty input → the §5.3 empty result; `summarize_expenses("nope")` raises `TypeError`; `summarize_expenses({...single record...})` raises `TypeError`; a generator input works (records consumed once); `ExpenseSummary` and `ValidatedExpense` are frozen (assignment raises `dataclasses.FrozenInstanceError`); the §7 worked example verbatim.

---

## 9. Non-goals

No currency conversion, no FX rates, no I/O or file parsing, no logging, no CLI, no per-record rounding in `ValidatedExpense`, no timezone or datetime-granularity support, no localization of category names.

---

Two open calls I made that you may want to overrule before implementation starts:

1. **Return floats, not `Decimal`,** in `ExpenseSummary`. Ergonomic and safely testable (a 2-dp `Decimal` maps to the nearest double, so `== 20.01` holds), but it does mean the public type is lossy. Say the word and I'll switch `totals`/`grand_total` to `Decimal`.
2. **Case-sensitive categories** and **strict `^[A-Z]{3}$` currency** (no `"usd"` coercion). Both are deliberately unforgiving; real-world input often needs normalization instead.