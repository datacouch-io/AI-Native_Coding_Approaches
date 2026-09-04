"""expenses.py — Expense report summarizer.

Implements API Contract v1.0 (frozen). Stdlib only.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
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

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExpenseError(Exception):
    """Base class for all expense-related errors."""


class RecordError(ExpenseError):
    def __init__(self, reason: str, field: str | None = None, index: int | None = None) -> None:
        super().__init__(f"record error: {reason} (field={field!r}, index={index!r})")
        self.reason = reason
        self.field = field
        self.index = index


class DateRangeError(ExpenseError):
    """Raised when start/end range parameters are invalid."""


class MixedCurrencyError(ExpenseError):
    def __init__(self, currencies: Iterable[str]) -> None:
        resolved = tuple(sorted(set(currencies)))
        super().__init__(f"mixed currencies in summary: {resolved!r}")
        self.currencies = resolved


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedExpense:
    date: date
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
    """Coerce a value to an unrounded Decimal per contract section 2.1.

    Raises TypeError for bool or unsupported types.
    Raises ValueError if a string cannot be parsed as a Decimal.
    Does NOT check finiteness or sign - callers are responsible for that.
    """
    if isinstance(value, bool):
        raise TypeError("bool is not a valid amount")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"unparseable amount string: {value!r}") from exc
    raise TypeError(f"unsupported amount type: {type(value)!r}")


def _parse_strict_date(value: Any) -> date:
    """Parse a date using the strict YYYY-MM-DD regex + calendar validation.

    Raises ValueError if value is not a str, doesn't match the pattern, or
    is not a real calendar date.
    """
    if not isinstance(value, str):
        raise ValueError(f"date must be a str, got {type(value)!r}")
    if not _DATE_RE.fullmatch(value):
        raise ValueError(f"date does not match YYYY-MM-DD pattern: {value!r}")
    return date.fromisoformat(value)


def _coerce_range_bound(value: Any) -> date | None:
    """Coerce a start/end range parameter per contract section 5.3 step 1."""
    if value is None:
        return None
    if isinstance(value, datetime):
        raise DateRangeError(f"datetime.datetime is not accepted as a range bound: {value!r}")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return _parse_strict_date(value)
        except ValueError as exc:
            raise DateRangeError(f"invalid range bound string: {value!r}") from exc
    raise DateRangeError(f"invalid type for range bound: {type(value)!r}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def round_money(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("round_money does not accept bool")
    try:
        amount = _coerce_amount(value)
    except TypeError as exc:
        raise ValueError(f"cannot coerce value to Decimal amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"amount is not finite: {value!r}")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def validate_record(record: Any, index: int | None = None) -> ValidatedExpense:
    if not isinstance(record, Mapping):
        raise RecordError("not_a_mapping", field=None, index=index)

    for key in ("date", "amount", "category", "currency"):
        if key not in record:
            raise RecordError("missing_field", field=key, index=index)

    try:
        parsed_date = _parse_strict_date(record["date"])
    except ValueError:
        raise RecordError("invalid_date", field="date", index=index)

    try:
        amount = _coerce_amount(record["amount"])
    except (TypeError, ValueError):
        raise RecordError("invalid_amount", field="amount", index=index)
    if not amount.is_finite():
        raise RecordError("invalid_amount", field="amount", index=index)
    if amount < 0:
        raise RecordError("negative_amount", field="amount", index=index)

    category_val = record["category"]
    if not isinstance(category_val, str) or not category_val.strip():
        raise RecordError("invalid_category", field="category", index=index)
    category = category_val.strip()

    currency_val = record["currency"]
    if not isinstance(currency_val, str) or not _CURRENCY_RE.fullmatch(currency_val):
        raise RecordError("invalid_currency", field="currency", index=index)

    return ValidatedExpense(date=parsed_date, amount=amount, category=category, currency=currency_val)


def summarize_expenses(
    records: Iterable[Mapping[str, Any]],
    *,
    start: str | date | None = None,
    end: str | date | None = None,
    strict: bool = False,
) -> ExpenseSummary:
    start_date = _coerce_range_bound(start)
    end_date = _coerce_range_bound(end)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise DateRangeError(f"start ({start_date}) is after end ({end_date})")

    if isinstance(records, (str, bytes)):
        raise TypeError("records must be an iterable of mapping records, not str/bytes")
    if isinstance(records, Mapping):
        raise TypeError("records must be an iterable of mapping records, not a single mapping")
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise TypeError("records is not iterable") from exc

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
                RejectedRecord(index=index, record=record, reason=exc.reason, field=exc.field)
            )
            continue

        if start_date is not None and validated.date < start_date:
            filtered_out_count += 1
            continue
        if end_date is not None and validated.date > end_date:
            filtered_out_count += 1
            continue

        accepted.append(validated)

    currencies = sorted({v.currency for v in accepted})
    if len(currencies) > 1:
        raise MixedCurrencyError(currencies)
    currency = currencies[0] if currencies else None

    totals_dec: dict[str, Decimal] = {}
    for v in accepted:
        totals_dec[v.category] = totals_dec.get(v.category, Decimal("0")) + v.amount

    rounded_totals: dict[str, Decimal] = {
        category: totals_dec[category].quantize(MONEY_QUANTUM, rounding=ROUNDING)
        for category in totals_dec
    }

    grand_total_dec = Decimal("0")
    for cat_total in rounded_totals.values():
        grand_total_dec += cat_total
    grand_total_dec = grand_total_dec.quantize(MONEY_QUANTUM, rounding=ROUNDING)

    totals_float: dict[str, float] = {
        category: float(rounded_totals[category]) for category in sorted(rounded_totals)
    }

    return ExpenseSummary(
        totals=totals_float,
        currency=currency,
        grand_total=float(grand_total_dec),
        accepted_count=len(accepted),
        filtered_out_count=filtered_out_count,
        rejected=tuple(rejected),
    )
