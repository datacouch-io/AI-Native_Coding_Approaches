```python
from datetime import datetime, timezone

import pytest

# Adjust this import to match your project structure.
from your_module import parse_iso8601


def test_parses_timezone_aware_timestamp() -> None:
    result = parse_iso8601("2026-09-04T12:34:56+02:00")

    assert result == datetime(2026, 9, 4, 12, 34, 56, tzinfo=timezone.utc)
    # If the parser preserves the original offset rather than normalizing to UTC,
    # use this assertion instead:
    # assert result == datetime(2026, 9, 4, 12, 34, 56, tzinfo=timezone(timedelta(hours=2)))


def test_rejects_timestamp_without_timezone() -> None:
    with pytest.raises(ValueError):
        parse_iso8601("2026-09-04T12:34:56")


def test_parses_fractional_seconds() -> None:
    result = parse_iso8601("2026-09-04T12:34:56.123456+00:00")

    assert result == datetime(
        2026, 9, 4, 12, 34, 56, 123456, tzinfo=timezone.utc
    )


def test_parses_zulu_suffix_as_utc() -> None:
    result = parse_iso8601("2026-09-04T12:34:56Z")

    assert result == datetime(2026, 9, 4, 12, 34, 56, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-timestamp",
        "2026/09/04 12:34:56Z",
        "2026-13-04T12:34:56Z",
        "2026-09-04T25:34:56Z",
    ],
)
def test_rejects_invalid_iso8601_format(value: str) -> None:
    with pytest.raises(ValueError):
        parse_iso8601(value)
```