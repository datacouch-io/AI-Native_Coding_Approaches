# Handoff state

## Public API of expenses.py (extracted from the code)

```python
class ExpenseError(ValueError):
class Expense:
def parse_expense(record: Mapping[str, Any]) -> Expense
def validate_expenses(records: Iterable[Mapping[str, Any]]) -> list[Expense]
def filter_by_date_range(expenses: Iterable[Expense], start: Any=None, end: Any=None) -> list[Expense]
def summarize_by_category(expenses: Iterable[Expense]) -> dict[str, float]
def summarize(records: Iterable[Mapping[str, Any]], start: Any=None, end: Any=None) -> dict[str, float]
```
