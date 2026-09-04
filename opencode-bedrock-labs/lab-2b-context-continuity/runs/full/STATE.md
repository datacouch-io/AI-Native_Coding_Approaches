# Handoff state

## Public API of expenses.py (extracted from the code)

```python
_DATE_RE = ...
_CURRENCY_RE = ...
class ExpenseError(Exception):
class RecordError(ExpenseError):
class DateRangeError(ExpenseError):
class MixedCurrencyError(ExpenseError):
class ValidatedExpense:
class RejectedRecord:
class ExpenseSummary:
def round_money(value: Decimal | int | float | str) -> Decimal
def validate_record(record: Any, index: int | None=None) -> ValidatedExpense
def summarize_expenses(records: Iterable[Mapping[str, Any]], *, start: str | date | None=None, end: str | date | None=None, strict: bool=False) -> ExpenseSummary
```
