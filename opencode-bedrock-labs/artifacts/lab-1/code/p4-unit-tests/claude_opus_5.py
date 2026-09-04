"""Unit tests for parse_iso8601(s: str) -> datetime."""

from datetime import datetime, timedelta, timezone

import pytest

# Adjust to the real module path.
from mymodule import parse_iso8601


UTC = timezone.utc


# ---------------------------------------------------------------- happy path

@pytest.mark.parametrize(
    "text, expected",
    [
        # Basic aware timestamp with explicit offset.
        ("2024-03-01T12:34:56+00:00", datetime(2024, 3, 1, 12, 34, 56, tzinfo=UTC)),
        (
            "2024-03-01T12:34:56+05:30",
            datetime(2024, 3, 1, 12, 34, 56, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        ),
        (
            "2024-03-01T12:34:56-08:00",
            datetime(2024, 3, 1, 12, 34, 56, tzinfo=timezone(timedelta(hours=-8))),
        ),
        # Leap day, and end-of-year boundary.
        ("2024-02-29T00:00:00Z", datetime(2024, 2, 29, 0, 0, 0, tzinfo=UTC)),
        ("2023-12-31T23:59:59Z", datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC)),
    ],
)
def test_parses_valid_timestamps(text, expected):
    assert parse_iso8601(text) == expected


# ------------------------------------------------- edge case 1: 'Z' suffix

class TestZSuffix:
    def test_z_maps_to_utc(self):
        result = parse_iso8601("2024-03-01T12:34:56Z")
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)
        assert result == datetime(2024, 3, 1, 12, 34, 56, tzinfo=UTC)

    def test_lowercase_z_accepted(self):
        # ISO-8601 designators are case-insensitive in practice; many parsers
        # accept 'z'. If the contract rejects it, invert this assertion.
        assert parse_iso8601("2024-03-01T12:34:56z") == datetime(
            2024, 3, 1, 12, 34, 56, tzinfo=UTC
        )

    def test_z_is_equivalent_to_plus_zero_offset(self):
        assert parse_iso8601("2024-03-01T12:34:56Z") == parse_iso8601(
            "2024-03-01T12:34:56+00:00"
        )

    def test_z_and_offset_cannot_both_appear(self):
        with pytest.raises(ValueError):
            parse_iso8601("2024-03-01T12:34:56Z+02:00")


# ------------------------------------------- edge case 2: missing timezone

class TestMissingTimezone:
    def test_naive_when_no_offset_present(self):
        result = parse_iso8601("2024-03-01T12:34:56")
        assert result.tzinfo is None
        assert result == datetime(2024, 3, 1, 12, 34, 56)

    def test_naive_is_not_silently_treated_as_utc(self):
        naive = parse_iso8601("2024-03-01T12:34:56")
        aware = parse_iso8601("2024-03-01T12:34:56Z")
        # Comparing naive and aware datetimes must raise, proving they differ.
        with pytest.raises(TypeError):
            _ = naive < aware

    def test_date_only_defaults_to_midnight_naive(self):
        result = parse_iso8601("2024-03-01")
        assert result == datetime(2024, 3, 1, 0, 0, 0)
        assert result.tzinfo is None


# ---------------------------------------- edge case 3: fractional seconds

class TestFractionalSeconds:
    @pytest.mark.parametrize(
        "text, expected_microsecond",
        [
            ("2024-03-01T12:34:56.5Z", 500_000),
            ("2024-03-01T12:34:56.05Z", 50_000),
            ("2024-03-01T12:34:56.123Z", 123_000),
            ("2024-03-01T12:34:56.123456Z", 123_456),
            ("2024-03-01T12:34:56.000000Z", 0),
        ],
    )
    def test_fraction_scales_to_microseconds(self, text, expected_microsecond):
        assert parse_iso8601(text).microsecond == expected_microsecond

    def test_precision_beyond_microseconds_is_truncated_not_an_error(self):
        # Nanosecond input is common (Go, Java, Postgres); must not explode.
        result = parse_iso8601("2024-03-01T12:34:56.123456789Z")
        assert result.microsecond == 123_456

    def test_comma_decimal_separator(self):
        # ISO-8601 permits ',' as the decimal sign.
        assert parse_iso8601("2024-03-01T12:34:56,250Z").microsecond == 250_000

    def test_fraction_combined_with_offset(self):
        assert parse_iso8601("2024-03-01T12:34:56.750+02:00") == datetime(
            2024, 3, 1, 12, 34, 56, 750_000, tzinfo=timezone(timedelta(hours=2))
        )

    def test_trailing_dot_without_digits_is_invalid(self):
        with pytest.raises(ValueError):
            parse_iso8601("2024-03-01T12:34:56.Z")


# ------------------------------------------- edge case 4: invalid formats

class TestInvalidInput:
    @pytest.mark.parametrize(
        "text",
        [
            "",                             # empty
            "   ",                          # whitespace only
            "not-a-timestamp",              # garbage
            "2024-03-01T12:34:56+25:00",    # offset out of range
            "2024-03-01T25:00:00Z",         # hour out of range
            "2024-03-01T12:60:00Z",         # minute out of range
            "2024-13-01T12:00:00Z",         # month out of range
            "2024-02-30T12:00:00Z",         # day not in month
            "2023-02-29T12:00:00Z",         # not a leap year
            "01/03/2024 12:34:56",          # wrong format entirely
            "2024-03-01 12:34:56Z",         # space separator instead of 'T'
            "2024-03-01T12:34:56Z trailing",  # trailing junk
            "2024-3-1T12:34:56Z",           # unpadded components
        ],
    )
    def test_invalid_strings_raise_value_error(self, text):
        with pytest.raises(ValueError):
            parse_iso8601(text)

    def test_error_message_includes_offending_input(self):
        with pytest.raises(ValueError, match="not-a-timestamp"):
            parse_iso8601("not-a-timestamp")

    @pytest.mark.parametrize("value", [None, 1709295296, 3.14, b"2024-03-01T12:34:56Z", object()])
    def test_non_string_input_raises_type_error(self, value):
        with pytest.raises(TypeError):
            parse_iso8601(value)


# -------------------------------------------------------------- properties

def test_parsing_is_idempotent_through_isoformat():
    text = "2024-03-01T12:34:56.123456+02:00"
    once = parse_iso8601(text)
    twice = parse_iso8601(once.isoformat())
    assert once == twice


def test_equal_instants_across_different_offsets():
    a = parse_iso8601("2024-03-01T12:00:00+00:00")
    b = parse_iso8601("2024-03-01T14:00:00+02:00")
    assert a == b
    assert a.utcoffset() != b.utcoffset()
