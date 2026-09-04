```python
from datetime import datetime, timedelta, timezone

import pytest

from your_module import parse_iso8601


def test_parses_z_suffix_as_utc():
    result = parse_iso8601("2026-09-04T14:30:00Z")

    assert result == datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)


def test_parses_fractional_seconds():
    result = parse_iso8601("2026-09-04T14:30:00.123456+00:00")

    assert result == datetime(
        2026, 9, 4, 14, 30, 0, 123456, tzinfo=timezone.utc
    )


def test_parses_timezone_offset():
    result = parse_iso8601("2026-09-04T14:30:00+05:30")

    expected_timezone = timezone(timedelta(hours=5, minutes=30))
    assert result == datetime(
        2026, 9, 4, 14, 30, tzinfo=expected_timezone
    )


def test_rejects_missing_timezone():
    with pytest.raises(ValueError):
        parse_iso8601("2026-09-04T14:30:00")


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        "not-a-timestamp",
        "2026-13-04T14:30:00Z",
        "2026-09-04 14:30:00 UTC",
        "",
    ],
)
def test_rejects_invalid_format(invalid_timestamp):
    with pytest.raises(ValueError):
        parse_iso8601(invalid_timestamp)
```