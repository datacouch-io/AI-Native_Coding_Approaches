Here's a pytest test suite for `parse_iso8601(s: str) -> datetime`, covering standard cases plus edge cases: missing timezone, fractional seconds, `Z` suffix, and invalid formats.

```python
import pytest
from datetime import datetime, timezone, timedelta

from your_module import parse_iso8601  # adjust import to actual module path


class TestParseIso8601Basic:
    def test_basic_datetime_with_offset(self):
        result = parse_iso8601("2023-06-15T14:30:00+02:00")
        assert result == datetime(2023, 6, 15, 14, 30, 0, tzinfo=timezone(timedelta(hours=2)))

    def test_date_only_midnight(self):
        # Depending on spec, date-only strings may parse to midnight.
        result = parse_iso8601("2023-06-15")
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 0
        assert result.minute == 0


class TestZSuffix:
    def test_z_suffix_is_utc(self):
        result = parse_iso8601("2023-06-15T14:30:00Z")
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)
        assert result == datetime(2023, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

    def test_z_suffix_with_fractional_seconds(self):
        result = parse_iso8601("2023-06-15T14:30:00.500Z")
        assert result.microsecond == 500000
        assert result.tzinfo == timezone.utc


class TestFractionalSeconds:
    def test_fractional_seconds_milliseconds(self):
        result = parse_iso8601("2023-06-15T14:30:00.123+00:00")
        assert result.microsecond == 123000

    def test_fractional_seconds_microseconds(self):
        result = parse_iso8601("2023-06-15T14:30:00.123456+00:00")
        assert result.microsecond == 123456

    def test_fractional_seconds_variable_precision(self):
        # 1-digit fractional second should scale correctly (e.g. .5 -> 500000 us)
        result = parse_iso8601("2023-06-15T14:30:00.5+00:00")
        assert result.microsecond == 500000


class TestMissingTimezone:
    def test_missing_timezone_is_naive(self):
        result = parse_iso8601("2023-06-15T14:30:00")
        assert result.tzinfo is None
        assert result == datetime(2023, 6, 15, 14, 30, 0)

    def test_missing_timezone_with_fractional_seconds(self):
        result = parse_iso8601("2023-06-15T14:30:00.250")
        assert result.tzinfo is None
        assert result.microsecond == 250000


class TestNegativeOffset:
    def test_negative_utc_offset(self):
        result = parse_iso8601("2023-06-15T14:30:00-05:00")
        assert result.utcoffset() == timedelta(hours=-5)

    def test_offset_without_colon(self):
        # Some ISO-8601 variants allow +HHMM instead of +HH:MM
        result = parse_iso8601("2023-06-15T14:30:00+0200")
        assert result.utcoffset() == timedelta(hours=2)


class TestInvalidFormats:
    @pytest.mark.parametrize("bad_input", [
        "",
        "not-a-date",
        "2023-13-01T00:00:00Z",   # invalid month
        "2023-06-32T00:00:00Z",   # invalid day
        "2023-06-15T25:00:00Z",   # invalid hour
        "2023-06-15T14:60:00Z",   # invalid minute
        "2023/06/15T14:30:00Z",   # wrong date separators
        "2023-06-15 14:30:00Z",   # space instead of T (if not supported)
        "2023-06-15T14:30:00+25:00",  # invalid offset
        None,
    ])
    def test_invalid_formats_raise(self, bad_input):
        with pytest.raises((ValueError, TypeError)):
            parse_iso8601(bad_input)


class TestRoundTrip:
    def test_roundtrip_isoformat(self):
        original = "2023-06-15T14:30:00.123456+02:00"
        result = parse_iso8601(original)
        assert result.isoformat() == original
```

Notes:
- Adjust the `from your_module import parse_iso8601` line to match the actual module path.
- Some assumptions are encoded as tests (e.g., date-only strings parsing to midnight, `+HHMM` without colon being valid, space instead of `T` being invalid). If your implementation's actual spec differs, flip the assertion or expected exception accordingly.
- The invalid-format parametrized test assumes the function raises `ValueError` or `TypeError` on bad input — update to match your function's actual error-handling contract (e.g., it might raise a custom exception).