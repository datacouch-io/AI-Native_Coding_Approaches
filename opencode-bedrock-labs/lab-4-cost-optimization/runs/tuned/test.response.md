```python
"""Test suite for durations.py.

Covers the parsing/formatting contract, all documented error cases,
and the round-trip property between parse_duration and format_duration.
"""

import random

import pytest

from durations import DurationError, format_duration, parse_duration


# ---------------------------------------------------------------------------
# parse_duration: valid inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("1h30m", 5400),
        ("1h 30m", 5400),
        ("2d4h", 2 * 86400 + 4 * 3600),
        ("90s", 90),
        ("45", 45),
        ("0", 0),
        ("0s", 0),
        ("1d", 86400),
        ("1H30M", 5400),  # case-insensitive
        ("1h30M", 5400),  # mixed case
        (" 1h30m ", 5400),  # leading/trailing whitespace
        ("   90s   ", 90),
        ("1d 30s", 86400 + 30),  # non-contiguous units, largest-to-smallest
        ("1d1h1m1s", 86400 + 3600 + 60 + 1),
        ("2d 4h 6m 8s", 2 * 86400 + 4 * 3600 + 6 * 60 + 8),
        ("1m", 60),
        ("1s", 1),
        ("100", 100),
    ],
)
def test_parse_duration_valid(text, expected):
    assert parse_duration(text) == expected


def test_parse_duration_units_need_not_be_contiguous():
    # d then straight to s, skipping h and m
    assert parse_duration("1d30s") == 86400 + 30


def test_parse_duration_allows_multiple_spaces_between_components():
    assert parse_duration("1h    30m") == 5400


# ---------------------------------------------------------------------------
# parse_duration: error cases
# ---------------------------------------------------------------------------

def test_parse_duration_rejects_empty_string():
    with pytest.raises(DurationError):
        parse_duration("")


def test_parse_duration_rejects_whitespace_only_string():
    with pytest.raises(DurationError):
        parse_duration("    ")


@pytest.mark.parametrize("value", [123, None, 3.5, [], {}, ("1h",)])
def test_parse_duration_rejects_non_string_input(value):
    with pytest.raises(DurationError):
        parse_duration(value)


def test_parse_duration_rejects_unknown_unit():
    with pytest.raises(DurationError):
        parse_duration("5w")


def test_parse_duration_rejects_repeated_unit():
    with pytest.raises(DurationError):
        parse_duration("1h2h")


@pytest.mark.parametrize("text", ["-5m", "-5", "1h-30m"])
def test_parse_duration_rejects_negative_value(text):
    with pytest.raises(DurationError):
        parse_duration(text)


def test_parse_duration_rejects_bare_unit_with_no_number():
    with pytest.raises(DurationError):
        parse_duration("h")


def test_parse_duration_rejects_trailing_garbage():
    # "30" after "1h" has no unit and is not the whole string.
    with pytest.raises(DurationError):
        parse_duration("1h30")


def test_parse_duration_rejects_out_of_order_units():
    with pytest.raises(DurationError):
        parse_duration("1m1h")


def test_parse_duration_rejects_garbage_text():
    with pytest.raises(DurationError):
        parse_duration("not a duration")


# ---------------------------------------------------------------------------
# format_duration: valid inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "seconds, expected",
    [
        (5400, "1h30m"),
        (45, "45s"),
        (0, "0s"),
        (86400, "1d"),
        (3600, "1h"),
        (60, "1m"),
        (1, "1s"),
        (61, "1m1s"),
        (90061, "1d1h1m1s"),
        (86461, "1d1m1s"),  # zero-hour component omitted
        (2 * 86400 + 4 * 3600 + 6 * 60 + 8, "2d4h6m8s"),
    ],
)
def test_format_duration_valid(seconds, expected):
    assert format_duration(seconds) == expected


def test_format_duration_omits_zero_components():
    # 1 day + 5 seconds: h and m components must be omitted, not "1d0h0m5s"
    assert format_duration(86400 + 5) == "1d5s"


# ---------------------------------------------------------------------------
# format_duration: error cases
# ---------------------------------------------------------------------------

def test_format_duration_rejects_negative():
    with pytest.raises(DurationError):
        format_duration(-5)


@pytest.mark.parametrize("value", [1.5, "5", None, [], 3.0])
def test_format_duration_rejects_non_integer(value):
    with pytest.raises(DurationError):
        format_duration(value)


def test_format_duration_rejects_bool():
    # bool is technically an int subclass but must not be accepted.
    with pytest.raises(DurationError):
        format_duration(True)


# ---------------------------------------------------------------------------
# Round-trip property: parse_duration(format_duration(n)) == n
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "n",
    [
        0, 1, 2, 30, 45, 59, 60, 61, 90,
        3599, 3600, 3601, 3661,
        86399, 86400, 86401, 86461, 90061,
        2 * 86400 + 4 * 3600 + 6 * 60 + 8,
        7 * 86400,
        123456,
        999999,
    ],
)
def test_round_trip_specific_values(n):
    assert parse_duration(format_duration(n)) == n


def test_round_trip_over_range():
    for n in range(0, 20000):
        assert parse_duration(format_duration(n)) == n


def test_round_trip_random_sample():
    rng = random.Random(12345)
    for _ in range(2000):
        n = rng.randint(0, 10_000_000)
        assert parse_duration(format_duration(n)) == n


def test_format_then_parse_case_insensitivity():
    formatted = format_duration(5400)
    assert parse_duration(formatted.upper()) == 5400
    assert parse_duration(formatted.lower()) == 5400
```