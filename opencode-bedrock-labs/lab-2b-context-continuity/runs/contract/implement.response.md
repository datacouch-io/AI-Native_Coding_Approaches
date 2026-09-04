All logic checks out. Since I'm in plan-mode (read-only, no file writes) but the request is simply to output the module's source as a text code block in my reply — not to create a file on disk — I can deliver that directly.

```python
"""Expense report summarizer.

Implements the frozen API contract v1.0 for expense record validation and
summarization. Stdlib only, no third-party dependencies.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

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

MONEY_QUANTUM: Decimal = Decimal("0.01")
ROUNDING: str = ROUND_HALF_EVEN

# Fixed-length date pattern; matched with .fullmatch() so no anchors needed.
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Exactly three uppercase ASCII letters; matched with .fullmatch().
_CURRENCY_RE = re.compile(r"[A-Z]{3}")

_MISSING_FIELD_ORDER = ("date", "amount", "category", "currency")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExpenseError(Exception):
    """Base class for all expense-related errors."""


class RecordError(ExpenseError):
    def __init__(
        self,
        reason: str,
        field: str | None = None,
        index: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.field = field
        self.index = index


class DateRangeError(ExpenseError):
    pass


class MixedCurrencyError(ExpenseError):
    def __init__(self, currencies: Iterable[str]) -> None:
        currencies = tuple(sorted(set(currencies)))
        super().__init__(f"mixed currencies: {currencies!r}")
        self.currencies = currencies


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedExpense:
    date: datetime.date
    amount: Decimal
    category: str
    currency: str


@dataclass(frozen=True)
class RejectedRecord:
    index: int
    record: Any
    reason: str
    field: str | None


@dataclass(frozen=True)
class ExpenseSummary:
    totals: dict[str, float]
    currency: str | None
    grand_total: float
    accepted_count: int
    filtered_out_count: int
    rejected: tuple[RejectedRecord, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_amount(value: Any) -> Decimal:
    """Coerce a raw amount value into a Decimal per the §2.1 rules.

    Raises TypeError for unsupported types (including bool), ValueError for
    unparseable strings. Does NOT check finiteness or sign; callers must do
    that afterwards.
    """
    if isinstance(value, bool):
        raise TypeError("bool is not a valid amount")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Never Decimal(float) directly -- go through str() to avoid
        # exposing binary floating point noise.
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return Decimal(stripped)
        except InvalidOperation as exc:
            raise ValueError("unparseable amount string") from exc
    raise TypeError(f"unsupported amount type: {type(value)!r}")


def _parse_strict_iso_date(value: Any) -> datetime.date:
    """Strict date parsing: regex format check, then calendar validation.

    Raises ValueError on any failure (wrong type, wrong format, or an
    invalid calendar date).
    """
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    if not _DATE_RE.fullmatch(value):
        raise ValueError("date does not match YYYY-MM-DD format")
    return datetime.date.fromisoformat(value)


def _coerce_range_bound(value: Any) -> datetime.date | None:
    """Coerce a start/end bound per §5.3 step 1. Raises DateRangeError."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        # datetime is a subclass of date -- must be rejected explicitly.
        raise DateRangeError("datetime.datetime is not a valid range bound")
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        if not _DATE_RE.fullmatch(value):
            raise DateRangeError(f"invalid date string: {value!r}")
        try:
            return datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise DateRangeError(f"invalid date string: {value!r}") from exc
    raise DateRangeError(f"unsupported range bound type: {type(value)!r}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def round_money(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("bool is not a valid amount")
    try:
        amount = _coerce_amount(value)
    except ValueError as exc:
        raise ValueError("unparseable amount") from exc
    if not amount.is_finite():
        raise ValueError("amount is not finite")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def validate_record(record: Any, index: int | None = None) -> ValidatedExpense:
    if not isinstance(record, Mapping):
        raise RecordError("not_a_mapping", None, index)

    for key in _MISSING_FIELD_ORDER:
        if key not in record:
            raise RecordError("missing_field", key, index)

    try:
        date_obj = _parse_strict_iso_date(record["date"])
    except ValueError:
        raise RecordError("invalid_date", "date", index)

    try:
        amount = _coerce_amount(record["amount"])
    except (TypeError, ValueError):
        raise RecordError("invalid_amount", "amount", index)
    if not amount.is_finite():
        raise RecordError("invalid_amount", "amount", index)
    if amount < 0:
        raise RecordError("negative_amount", "amount", index)

    category_value = record["category"]
    if not isinstance(category_value, str):
        raise RecordError("invalid_category", "category", index)
    category = category_value.strip()
    if not category:
        raise RecordError("invalid_category", "category", index)

    currency_value = record["currency"]
    if not isinstance(currency_value, str) or not _CURRENCY_RE.fullmatch(currency_value):
        raise RecordError("invalid_currency", "currency", index)

    return ValidatedExpense(
        date=date_obj,
        amount=amount,
        category=category,
        currency=currency_value,
    )


def summarize_expenses(
    records: Iterable[Mapping[str, Any]],
    *,
    start: str | datetime.date | None = None,
    end: str | datetime.date | None = None,
    strict: bool = False,
) -> ExpenseSummary:
    # 1. Range params.
    start_date = _coerce_range_bound(start)
    end_date = _coerce_range_bound(end)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise DateRangeError("start is after end")

    # 2. Input type.
    if isinstance(records, (str, bytes)):
        raise TypeError("records must be an iterable of mappings, not str/bytes")
    if isinstance(records, Mapping):
        raise TypeError(
            "records must be an iterable of mappings, not a single mapping"
        )
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise TypeError("records is not iterable") from exc

    # 3. Per record.
    rejected: list[RejectedRecord] = []
    accepted: list[ValidatedExpense] = []
    filtered_out_count = 0

    for index, record in enumerate(iterator):
        try:
            validated = validate_record(record, index)
        except RecordError as exc:
            if strict:
                raise
            rejected.append(
                RejectedRecord(
                    index=index,
                    record=record,
                    reason=exc.reason,
                    field=exc.field,
                )
            )
            continue

        if start_date is not None and validated.date < start_date:
            filtered_out_count += 1
            continue
        if end_date is not None and validated.date > end_date:
            filtered_out_count += 1
            continue

        accepted.append(validated)

    # 4. Currency check (accepted records only).
    currencies = sorted({expense.currency for expense in accepted})
    if len(currencies) > 1:
        raise MixedCurrencyError(currencies)
    currency = currencies[0] if currencies else None

    # 5. Totals: sum exact Decimal amounts per category, quantize once.
    category_sums: dict[str, Decimal] = {}
    for expense in accepted:
        category_sums.setdefault(expense.category, Decimal("0"))
        category_sums[expense.category] += expense.amount

    totals: dict[str, float] = {}
    grand_total_decimal = Decimal("0")
    for category in sorted(category_sums):
        rounded = category_sums[category].quantize(MONEY_QUANTUM, rounding=ROUNDING)
        totals[category] = float(rounded)
        grand_total_decimal += rounded

    # 6. Grand total: sum of already-rounded per-category totals, quantized.
    grand_total_decimal = grand_total_decimal.quantize(MONEY_QUANTUM, rounding=ROUNDING)

    return ExpenseSummary(
        totals=totals,
        currency=currency,
        grand_total=float(grand_total_decimal),
        accepted_count=len(accepted),
        filtered_out_count=filtered_out_count,
        rejected=tuple(rejected),
    )
```