"""Expense report summarizer.

Validates raw expense records, filters them to an inclusive date range,
and produces per-category totals using banker's rounding. Records that
are malformed are rejected rather than raising, but mixing currencies
within a single summary is treated as a hard error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Any, Iterable, Mapping


class ExpenseError(ValueError):
    """Raised for invalid expense data or summarization errors."""


@dataclass(frozen=True)
class Expense:
    """A single validated expense record."""

    date: date
    amount: Decimal
    category: str
    currency: str


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ExpenseError(f"Invalid date: {value!r}")

    text = value.strip()
    if not text:
        raise ExpenseError(f"Invalid date: {value!r}")

    # Support a trailing 'Z' (UTC) suffix, which datetime.fromisoformat
    # only accepts starting in Python 3.11.
    candidate = text[:-1] + "+00:00" if text[-1] in "Zz" else text

    try:
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ExpenseError(f"Invalid date: {value!r}") from exc


def _parse_amount(value: Any) -> Decimal:
    if isinstance(value, bool):
        # bool is a subclass of int; reject explicitly to avoid surprises.
        raise ExpenseError(f"Invalid amount: {value!r}")

    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ExpenseError(f"Invalid amount: {value!r}") from exc
    else:
        raise ExpenseError(f"Invalid amount: {value!r}")

    if amount.is_nan() or amount.is_infinite():
        raise ExpenseError(f"Invalid amount: {value!r}")
    if amount < 0:
        raise ExpenseError(f"Negative amount: {value!r}")
    return amount


def _parse_category(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExpenseError(f"Missing category: {value!r}")
    return value.strip()


def _parse_currency(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isalpha()
        or not value.isupper()
    ):
        raise ExpenseError(f"Invalid currency code: {value!r}")
    return value


def parse_expense(record: Mapping[str, Any]) -> Expense:
    """Validate and convert a raw record into an :class:`Expense`.

    Raises :class:`ExpenseError` if the record is malformed.
    """

    try:
        raw_date = record["date"]
        raw_amount = record["amount"]
        raw_category = record["category"]
        raw_currency = record["currency"]
    except (KeyError, TypeError) as exc:
        raise ExpenseError(f"Malformed record: {record!r}") from exc

    return Expense(
        date=_parse_date(raw_date),
        amount=_parse_amount(raw_amount),
        category=_parse_category(raw_category),
        currency=_parse_currency(raw_currency),
    )


def validate_expenses(records: Iterable[Mapping[str, Any]]) -> list[Expense]:
    """Return the subset of ``records`` that are well-formed expenses.

    Malformed records (bad date, non-numeric/negative amount, missing
    category, or invalid currency code) are silently skipped.
    """

    accepted: list[Expense] = []
    for record in records:
        try:
            accepted.append(parse_expense(record))
        except ExpenseError:
            continue
    return accepted


def filter_by_date_range(
    expenses: Iterable[Expense],
    start: Any = None,
    end: Any = None,
) -> list[Expense]:
    """Filter expenses to an inclusive ``[start, end]`` date range.

    ``start``/``end`` may be ``None`` (unbounded on that side), a
    ``date``/``datetime``, or an ISO-8601 string.
    """

    start_date = _parse_date(start) if start is not None else None
    end_date = _parse_date(end) if end is not None else None

    if start_date is not None and end_date is not None and start_date > end_date:
        raise ExpenseError("start date must not be after end date")

    result = []
    for expense in expenses:
        if start_date is not None and expense.date < start_date:
            continue
        if end_date is not None and expense.date > end_date:
            continue
        result.append(expense)
    return result


def _round_money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def summarize_by_category(expenses: Iterable[Expense]) -> dict[str, float]:
    """Produce per-category totals, rounded to 2dp with banker's rounding.

    All expenses passed in must share a single currency; if more than one
    currency is present, :class:`ExpenseError` is raised rather than
    silently summing incompatible amounts.
    """

    totals: dict[str, Decimal] = {}
    currencies: set[str] = set()

    for expense in expenses:
        currencies.add(expense.currency)
        totals[expense.category] = totals.get(expense.category, Decimal("0")) + expense.amount

    if len(currencies) > 1:
        raise ExpenseError(
            f"Cannot summarize mixed currencies in a single summary: {sorted(currencies)!r}"
        )

    return {category: float(_round_money(total)) for category, total in totals.items()}


def summarize(
    records: Iterable[Mapping[str, Any]],
    start: Any = None,
    end: Any = None,
) -> dict[str, float]:
    """End-to-end helper: validate, filter by date range, and summarize.

    Malformed records are dropped. Raises :class:`ExpenseError` if the
    remaining records span more than one currency.
    """

    expenses = validate_expenses(records)
    expenses = filter_by_date_range(expenses, start=start, end=end)
    return summarize_by_category(expenses)
