import dataclasses
import datetime
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
def test_round_money_uses_bankers_rounding(value, expected):
    assert round_money(value) == expected


def test_round_money_rejects_bool():
    with pytest.raises(TypeError):
        round_money(True)


@pytest.mark.parametrize("value", ["abc", float("nan")])
def test_round_money_rejects_unparseable_or_non_finite_values(value):
    with pytest.raises(ValueError):
        round_money(value)


def test_sum_then_rounds_once_per_category():
    summary = summarize_expenses(
        [
            record(amount=0.005, category="tips"),
            record(amount=0.005, category="tips"),
        ]
    )

    assert summary.totals == {"tips": 0.01}
    assert summary.grand_total == 0.01


def assert_record_error(record_value, reason, field, index=None):
    with pytest.raises(RecordError) as caught:
        validate_record(record_value, index=index)

    error = caught.value
    assert error.reason == reason
    assert error.field == field
    assert error.index == index


def test_validate_record_rejects_non_mapping():
    assert_record_error([], "not_a_mapping", None)


@pytest.mark.parametrize("missing_field", ["date", "amount", "category", "currency"])
def test_validate_record_rejects_each_missing_required_field(missing_field):
    value = record()
    del value[missing_field]

    assert_record_error(value, "missing_field", missing_field)


@pytest.mark.parametrize(
    "date_value",
    [
        "2024-13-01",
        "2024-1-5",
        "20240115",
        "2024-01-15T00:00:00",
        None,
    ],
)
def test_validate_record_rejects_invalid_dates(date_value):
    assert_record_error(record(date=date_value), "invalid_date", "date")


@pytest.mark.parametrize("amount", ["abc", None, True, float("inf")])
def test_validate_record_rejects_invalid_amounts(amount):
    assert_record_error(record(amount=amount), "invalid_amount", "amount")


def test_validate_record_rejects_negative_amount():
    assert_record_error(record(amount=-0.01), "negative_amount", "amount")


@pytest.mark.parametrize("category", ["", "   ", None])
def test_validate_record_rejects_invalid_categories(category):
    assert_record_error(record(category=category), "invalid_category", "category")


@pytest.mark.parametrize("currency", ["usd", "US", "USDD", "US1", None])
def test_validate_record_rejects_invalid_currencies(currency):
    assert_record_error(record(currency=currency), "invalid_currency", "currency")


def test_validation_precedence_prefers_date_before_currency():
    assert_record_error(
        record(date="not-a-date", currency="usd"),
        "invalid_date",
        "date",
    )


def test_validation_precedence_checks_missing_amount_before_currency():
    value = record()
    del value["amount"]
    del value["currency"]

    assert_record_error(value, "missing_field", "amount")


def test_validate_record_keeps_exact_unrounded_amount_and_normalizes_category():
    validated = validate_record(record(amount="10.005", category="  food  "))

    assert validated.amount == Decimal("10.005")
    assert validated.category == "food"
    assert validated.currency == "USD"
    assert validated.date == datetime.date(2024, 1, 15)


def test_accepted_amount_edges_and_extra_keys():
    summary = summarize_expenses(
        [
            record(amount=0, category="zero"),
            record(amount="1e2", category="scientific", extra="ignored"),
        ]
    )

    assert summary.totals == {"scientific": 100.0, "zero": 0.0}
    assert summary.accepted_count == 2


def test_totals_group_categories_sort_keys_and_keep_case_distinct():
    summary = summarize_expenses(
        [
            record(amount=1.005, category="food"),
            record(amount=2, category="Food"),
            record(amount=3, category="travel"),
            record(amount=0.005, category="food"),
        ]
    )

    assert list(summary.totals) == ["Food", "food", "travel"]
    assert summary.totals == {"Food": 2.0, "food": 1.01, "travel": 3.0}
    assert summary.grand_total == sum(summary.totals.values())


def test_date_range_is_inclusive_at_both_boundaries():
    summary = summarize_expenses(
        [
            record(date="2024-01-01", amount=1),
            record(date="2024-01-31", amount=2),
            record(date="2024-02-01", amount=3),
        ],
        start="2024-01-01",
        end="2024-01-31",
    )

    assert summary.totals == {"food": 3.0}
    assert summary.accepted_count == 2
    assert summary.filtered_out_count == 1


def test_start_only_date_range():
    summary = summarize_expenses(
        [
            record(date="2024-01-01", amount=1),
            record(date="2024-01-02", amount=2),
        ],
        start="2024-01-02",
    )

    assert summary.totals == {"food": 2.0}
    assert summary.filtered_out_count == 1


def test_end_only_date_range():
    summary = summarize_expenses(
        [
            record(date="2024-01-01", amount=1),
            record(date="2024-01-02", amount=2),
        ],
        end="2024-01-01",
    )

    assert summary.totals == {"food": 1.0}
    assert summary.filtered_out_count == 1


def test_no_date_range_accepts_all_valid_records():
    summary = summarize_expenses(
        [
            record(date="2024-01-01", amount=1),
            record(date="2025-01-01", amount=2),
        ]
    )

    assert summary.totals == {"food": 3.0}
    assert summary.filtered_out_count == 0


def test_date_range_excluding_everything_returns_empty_summary():
    summary = summarize_expenses(
        [record(date="2024-01-01")],
        start="2024-02-01",
        end="2024-02-28",
    )

    assert summary == ExpenseSummary(
        totals={},
        currency=None,
        grand_total=0.0,
        accepted_count=0,
        filtered_out_count=1,
        rejected=(),
    )


def test_invalid_date_range_parameters_raise_date_range_error():
    with pytest.raises(DateRangeError):
        summarize_expenses([], start="2024-02-01", end="2024-01-01")

    with pytest.raises(DateRangeError):
        summarize_expenses([], start="2024-1-1")

    with pytest.raises(DateRangeError):
        summarize_expenses([], start=datetime.datetime(2024, 1, 1))


def test_date_objects_are_accepted_as_range_parameters():
    summary = summarize_expenses(
        [record(date="2024-01-15")],
        start=datetime.date(2024, 1, 15),
        end=datetime.date(2024, 1, 15),
    )

    assert summary.accepted_count == 1
    assert summary.filtered_out_count == 0


def test_mixed_accepted_currencies_raise_with_sorted_deduplicated_currencies():
    with pytest.raises(MixedCurrencyError) as caught:
        summarize_expenses(
            [
                record(currency="USD"),
                record(currency="EUR"),
                record(currency="USD", category="travel"),
            ]
        )

    assert caught.value.currencies == ("EUR", "USD")


def test_rejected_record_currency_does_not_contribute_to_mixed_currency_check():
    summary = summarize_expenses(
        [
            record(currency="USD"),
            record(amount=-1, currency="EUR"),
        ]
    )

    assert summary.currency == "USD"
    assert [(item.index, item.reason) for item in summary.rejected] == [
        (1, "negative_amount")
    ]


def test_filtered_record_currency_does_not_contribute_to_mixed_currency_check():
    summary = summarize_expenses(
        [
            record(date="2024-01-15", currency="USD"),
            record(date="2023-12-31", currency="EUR"),
        ],
        start="2024-01-01",
        end="2024-01-31",
    )

    assert summary.currency == "USD"
    assert summary.filtered_out_count == 1


def test_single_currency_is_allowed_across_many_records():
    summary = summarize_expenses(
        [
            record(currency="USD", category="food"),
            record(currency="USD", category="travel"),
        ]
    )

    assert summary.currency == "USD"
    assert summary.accepted_count == 2


def test_strict_mode_raises_first_record_error_with_input_index():
    with pytest.raises(RecordError) as caught:
        summarize_expenses(
            [
                record(),
                record(amount=-1),
                record(date="not-a-date"),
            ],
            strict=True,
        )

    error = caught.value
    assert error.index == 1
    assert error.reason == "negative_amount"
    assert error.field == "amount"


def test_strict_mode_matches_non_strict_mode_for_all_valid_records():
    records = [
        record(amount=1.005, category="food"),
        record(amount=2, category="travel"),
    ]

    assert summarize_expenses(records, strict=True) == summarize_expenses(
        records, strict=False
    )


def test_empty_input_returns_empty_summary():
    assert summarize_expenses([]) == ExpenseSummary(
        totals={},
        currency=None,
        grand_total=0.0,
        accepted_count=0,
        filtered_out_count=0,
        rejected=(),
    )


def test_summary_rejects_string_and_single_mapping_inputs():
    with pytest.raises(TypeError):
        summarize_expenses("nope")

    with pytest.raises(TypeError):
        summarize_expenses(record())


def test_generator_input_is_consumed_once_and_summarized():
    def records():
        yield record(amount=1)
        yield record(amount=2)

    summary = summarize_expenses(records())

    assert summary.totals == {"food": 3.0}
    assert summary.accepted_count == 2


def test_summary_and_validated_expense_are_frozen():
    validated = validate_record(record())
    summary = summarize_expenses([])

    with pytest.raises(dataclasses.FrozenInstanceError):
        validated.category = "travel"

    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.currency = "USD"


def test_worked_example():
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
    assert [(item.index, item.reason, item.field) for item in summary.rejected] == [
        (4, "negative_amount", "amount"),
        (5, "invalid_date", "date"),
    ]
