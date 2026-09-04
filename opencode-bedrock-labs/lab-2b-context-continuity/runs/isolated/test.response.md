```python
from decimal import Decimal

import pytest

from expenses import summarize_expenses


def expense(date, amount, category, currency="USD"):
    return {
        "date": date,
        "amount": amount,
        "category": category,
        "currency": currency,
    }


def test_summarizes_accepted_expenses_by_category():
    records = [
        expense("2026-01-01", "12.50", "Meals"),
        expense("2026-01-02", Decimal("7.25"), "Meals"),
        expense("2026-01-03", 20, "Travel"),
    ]

    assert summarize_expenses(records) == {
        "Meals": Decimal("19.75"),
        "Travel": Decimal("20.00"),
    }


@pytest.mark.parametrize(
    "record",
    [
        expense("not-a-date", 10, "Meals"),
        expense("2026-02-30", 10, "Meals"),
        expense("2026-01-01", "ten", "Meals"),
        expense("2026-01-01", None, "Meals"),
        expense("2026-01-01", True, "Meals"),
        expense("2026-01-01", -0.01, "Meals"),
        expense("2026-01-01", 10, ""),
        expense("2026-01-01", 10, None),
        expense("2026-01-01", 10, "Meals", "usd"),
        expense("2026-01-01", 10, "Meals", "US"),
        expense("2026-01-01", 10, "Meals", "USDA"),
        expense("2026-01-01", 10, "Meals", "U5D"),
    ],
)
def test_rejects_malformed_records(record):
    with pytest.raises(ValueError):
        summarize_expenses([record])


def test_rounds_each_expense_to_two_places_using_bankers_rounding():
    records = [
        expense("2026-01-01", Decimal("1.005"), "Meals"),
        expense("2026-01-02", Decimal("2.675"), "Meals"),
        expense("2026-01-03", Decimal("3.015"), "Travel"),
    ]

    assert summarize_expenses(records) == {
        "Meals": Decimal("3.68"),
        "Travel": Decimal("3.02"),
    }


def test_filters_expenses_to_an_inclusive_date_range():
    records = [
        expense("2026-01-01", 10, "Meals"),
        expense("2026-01-02", 20, "Meals"),
        expense("2026-01-03", 30, "Travel"),
        expense("2026-01-04", 40, "Travel"),
    ]

    assert summarize_expenses(
        records,
        start_date="2026-01-02",
        end_date="2026-01-03",
    ) == {
        "Meals": Decimal("20.00"),
        "Travel": Decimal("30.00"),
    }


def test_rejects_mixed_currencies():
    records = [
        expense("2026-01-01", 10, "Meals", "USD"),
        expense("2026-01-02", 20, "Travel", "EUR"),
    ]

    with pytest.raises(ValueError, match="currency"):
        summarize_expenses(records)


def test_ignores_other_currency_records_outside_the_date_range():
    records = [
        expense("2026-01-01", 10, "Meals", "USD"),
        expense("2026-01-02", 20, "Travel", "EUR"),
    ]

    assert summarize_expenses(
        records,
        start_date="2026-01-01",
        end_date="2026-01-01",
    ) == {"Meals": Decimal("10.00")}
```