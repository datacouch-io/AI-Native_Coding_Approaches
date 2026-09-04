```python
import dataclasses
from datetime import date, datetime
from decimal import Decimal

import pytest

from expenses import (
    DateRangeError,
    ExpenseSummary,
    MixedCurrencyError,
    RecordError,
    ValidatedExpense,
    round_money,
    summarize_expenses,
    validate_record,
)


def record(**overrides):
    value = {
        "date": "2024-01-15",
        "amount": 10,
        "category": "food",
        "currency": "USD",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2.675, Decimal("2.68")),
        (2.665, Decimal("2.66")),
        (0.125, Decimal("0.12")),
        (0.135, Decimal("0.14")),
        (1.005, Decimal("1.00")),
        ("1.014", Decimal("1.01")),
        (10, Decimal("10.00")),
    ],
)
def test_round_money_uses_decimal_bankers_rounding(value, expected):
    assert round_money(value) == expected


def test_round_money_rejects_invalid_values():
    with pytest.raises(TypeError):
        round_money(True)

    with pytest.raises(ValueError):
        round_money("abc")

    with pytest.raises(ValueError):
        round_money(float("nan"))


def test_sum_then_rounds_once_per_category():
    summary = summarize_expenses(
        [
            record(amount=0.005, category="tips"),
            record(amount=0.005, category="tips"),
        ]
    )

    assert summary.totals == {"tips": 0.01}
    assert summary.grand_total == 0.01


def test_validate_record_rejects_non_mapping():
    with pytest.raises(RecordError) as raised:
        validate_record([])

    assert (raised.value.reason, raised.value.field, raised.value.index) == (
        "not_a_mapping",
        None,
        None,
    )


@pytest.mark.parametrize("missing_key", ["date", "amount", "category", "currency"])
def test_validate_record_rejects_each_missing_required_field(missing_key):
    invalid = record()
    del invalid[missing_key]

    with pytest.raises(RecordError) as raised:
        validate_record(invalid, index=4)

    assert (raised.value.reason, raised.value.field, raised.value.index) == (
        "missing_field",
        missing_key,
        4,
    )


@pytest.mark.parametrize(
    "invalid_date",
    ["2024-13-01", "2024-1-5", "20240115", "2024-01-15T00:00:00", 20240115],
)
def test_validate_record_rejects_invalid_dates(invalid_date):
    with pytest.raises(RecordError) as raised:
        validate_record(record(date=invalid_date))

    assert (raised.value.reason, raised.value.field) == ("invalid_date", "date")


@pytest.mark.parametrize("invalid_amount", ["abc", None, True, float("inf")])
def test_validate_record_rejects_invalid_amounts(invalid_amount):
    with pytest.raises(RecordError) as raised:
        validate_record(record(amount=invalid_amount))

    assert (raised.value.reason, raised.value.field) == ("invalid_amount", "amount")


def test_validate_record_rejects_negative_amount():
    with pytest.raises(RecordError) as raised:
        validate_record(record(amount=-0.01))

    assert (raised.value.reason, raised.value.field) == ("negative_amount", "amount")


@pytest.mark.parametrize("invalid_category", ["", "   ", 42])
def test_validate_record_rejects_invalid_categories(invalid_category):
    with pytest.raises(RecordError) as raised:
        validate_record(record(category=invalid_category))

    assert (raised.value.reason, raised.value.field) == (
        "invalid_category",
        "category",
    )


@pytest.mark.parametrize("invalid_currency", ["usd", "US", "USDD", "US1", 123])
def test_validate_record_rejects_invalid_currencies(invalid_currency):
    with pytest.raises(RecordError) as raised:
        validate_record(record(currency=invalid_currency))

    assert (raised.value.reason, raised.value.field) == (
        "invalid_currency",
        "currency",
    )


def test_validation_precedence_prefers_date_over_later_faults():
    with pytest.raises(RecordError) as raised:
        validate_record(record(date="not-a-date", currency="usd"))

    assert (raised.value.reason, raised.value.field) == ("invalid_date", "date")


def test_validation_precedence_checks_missing_fields_in_contract_order():
    invalid = record()
    del invalid["amount"]
    del invalid["currency"]

    with pytest.raises(RecordError) as raised:
        validate_record(invalid)

    assert (raised.value.reason, raised.value.field) == ("missing_field", "amount")


def test_accepted_edges_and_category_normalization():
    validated_zero = validate_record(record(amount=0))
    validated_scientific = validate_record(record(amount="1e2"))
    validated_extra = validate_record(record(extra="ignored"))
    validated_category = validate_record(record(category="  food  "))

    assert validated_zero.amount == Decimal("0")
    assert validated_scientific.amount == Decimal("1E+2")
    assert validated_extra.category == "food"
    assert validated_category.category == "food"

    summary = summarize_expenses(
        [
            record(amount=0, category="  food  "),
            record(amount="1e2", category="  food  "),
        ]
    )
    assert summary.totals == {"food": 100.0}


def test_totals_grouping_order_case_sensitivity_and_grand_total():
    summary = summarize_expenses(
        [
            record(amount="1.005", category="food"),
            record(amount="2.005", category="Food"),
            record(amount="3.004", category="travel"),
        ]
    )

    assert list(summary.totals) == ["Food", "food", "travel"]
    assert summary.totals == {"Food": 2.0, "food": 1.0, "travel": 3.0}
    assert summary.grand_total == sum(summary.totals.values())


def test_date_range_is_inclusive_and_counts_filtered_records():
    summary = summarize_expenses(
        [
            record(date="2024-01-01", amount=1),
            record(date="2024-01-15", amount=2),
            record(date="2024-01-31", amount=3),
            record(date="2023-12-31", amount=4),
            record(date="2024-02-01", amount=5),
        ],
        start="2024-01-01",
        end="2024-01-31",
    )

    assert summary.totals == {"food": 6.0}
    assert summary.accepted_count == 3
    assert summary.filtered_out_count == 2


def test_start_only_end_only_and_unbounded_ranges():
    records = [
        record(date="2024-01-01", amount=1),
        record(date="2024-01-15", amount=2),
        record(date="2024-01-31", amount=3),
    ]

    assert summarize_expenses(records, start="2024-01-15").grand_total == 5.0
    assert summarize_expenses(records, end="2024-01-15").grand_total == 3.0
    assert summarize_expenses(records).grand_total == 6.0


def test_range_excluding_everything_returns_empty_summary():
    summary = summarize_expenses(
        [record(date="2024-01-01")],
        start="2024-02-01",
        end="2024-02-02",
    )

    assert summary.totals == {}
    assert summary.currency is None
    assert summary.grand_total == 0.0
    assert summary.accepted_count == 0
    assert summary.filtered_out_count == 1


def test_date_range_errors_and_date_bound_acceptance():
    with pytest.raises(DateRangeError):
        summarize_expenses([], start="2024-02-01", end="2024-01-01")

    with pytest.raises(DateRangeError):
        summarize_expenses([], start="2024-1-1")

    with pytest.raises(DateRangeError):
        summarize_expenses([], start=datetime(2024, 1, 1))

    summary = summarize_expenses(
        [record(date="2024-01-15", amount=2)],
        start=date(2024, 1, 15),
        end=date(2024, 1, 15),
    )
    assert summary.grand_total == 2.0


def test_mixed_accepted_currencies_raise_with_sorted_currencies():
    with pytest.raises(MixedCurrencyError) as raised:
        summarize_expenses(
            [
                record(currency="USD"),
                record(currency="EUR"),
            ]
        )

    assert raised.value.currencies == ("EUR", "USD")


def test_rejected_and_filtered_currency_do_not_trigger_mixed_currency_error():
    rejected_summary = summarize_expenses(
        [
            record(currency="USD"),
            record(amount=-1, currency="EUR"),
        ]
    )
    assert rejected_summary.currency == "USD"

    filtered_summary = summarize_expenses(
        [
            record(date="2024-01-15", currency="USD"),
            record(date="2023-12-31", currency="EUR"),
        ],
        start="2024-01-01",
    )
    assert filtered_summary.currency == "USD"

    single_currency_summary = summarize_expenses(
        [record(amount=1), record(amount=2), record(amount=3)]
    )
    assert single_currency_summary.currency == "USD"


def test_strict_mode_raises_first_record_error_with_index():
    with pytest.raises(RecordError) as raised:
        summarize_expenses(
            [
                record(amount=-1),
                record(date="bad-date"),
            ],
            strict=True,
        )

    assert (raised.value.index, raised.value.reason, raised.value.field) == (
        0,
        "negative_amount",
        "amount",
    )


def test_strict_mode_valid_input_matches_non_strict_mode():
    records = [record(amount=1), record(amount=2, category="travel")]

    assert summarize_expenses(records, strict=True) == summarize_expenses(
        records, strict=False
    )


def test_empty_input_and_invalid_input_containers():
    assert summarize_expenses([]) == ExpenseSummary(
        totals={},
        currency=None,
        grand_total=0.0,
        accepted_count=0,
        filtered_out_count=0,
        rejected=(),
    )

    with pytest.raises(TypeError):
        summarize_expenses("nope")

    with pytest.raises(TypeError):
        summarize_expenses(record())


def test_generator_input_is_consumed_once():
    records = (record(amount=amount) for amount in [1, 2, 3])

    summary = summarize_expenses(records)

    assert summary.accepted_count == 3
    assert summary.grand_total == 6.0


def test_public_data_classes_are_frozen():
    validated = validate_record(record())
    summary = summarize_expenses([record()])

    with pytest.raises(dataclasses.FrozenInstanceError):
        validated.category = "travel"

    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.currency = "EUR"

    assert isinstance(validated, ValidatedExpense)
    assert isinstance(summary, ExpenseSummary)


def test_worked_example_verbatim():
    records = [
        {
            "date": "2024-01-05",
            "amount": 10.005,
            "category": "food",
            "currency": "USD",
        },
        {
            "date": "2024-01-06",
            "amount": 10.005,
            "category": "food",
            "currency": "USD",
        },
        {
            "date": "2024-01-07",
            "amount": "2.675",
            "category": "travel",
            "currency": "USD",
        },
        {
            "date": "2023-12-31",
            "amount": 99.0,
            "category": "travel",
            "currency": "USD",
        },
        {
            "date": "2024-01-08",
            "amount": -1.0,
            "category": "food",
            "currency": "USD",
        },
        {
            "date": "2024-13-01",
            "amount": 5.0,
            "category": "food",
            "currency": "USD",
        },
    ]

    summary = summarize_expenses(records, start="2024-01-01", end="2024-01-31")

    assert summary.totals == {"food": 20.01, "travel": 2.68}
    assert list(summary.totals) == ["food", "travel"]
    assert summary.currency == "USD"
    assert summary.grand_total == 22.69
    assert summary.accepted_count == 3
    assert summary.filtered_out_count == 1
    assert [(rejected.index, rejected.reason, rejected.field) for rejected in summary.rejected] == [
        (4, "negative_amount", "amount"),
        (5, "invalid_date", "date"),
    ]
```