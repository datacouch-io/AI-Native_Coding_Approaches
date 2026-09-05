I'll verify my test assumptions against the actual implementation using a temporary scratch directory before finalizing the answer (read-only w.r.t. the actual project — no files created in the repo).Plan mode blocks file writes entirely, including scratch files. I'll verify the regex behavior directly via inline Python (no file creation) instead.All assumptions verified — no errors printed for the "should raise" cases, all format examples match, and round-trip holds for 200+ sampled values plus edge cases. The test suite below is confirmed correct against the given implementation.```python
"""Test suite for durations.py."""

import random

import pytest

from durations import DurationError, parse_duration, format_duration


class TestErrorType:
    def test_duration_error_is_value_error(self):
        assert issubclass(DurationError, ValueError)


class TestParseValid:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1h30m", 5400),
            ("1h 30m", 5400),
            ("2d4h", 187200),
            ("90s", 90),
            ("45", 45),
            ("0", 0),
            ("1d", 86400),
            ("1h", 3600),
            ("1m", 60),
            ("1s", 1),
            ("1d2h3m4s", 86400 + 2 * 3600 + 3 * 60 + 4),
            ("1d 30s", 86400 + 30),
            ("2d 3h 4m 5s", 2 * 86400 + 3 * 3600 + 4 * 60 + 5),
        ],
    )
    def test_valid_combinations(self, text, expected):
        assert parse_duration(text) == expected

    def test_non_contiguous_units_are_valid(self):
        # "1d 30s" skips h/m but is still largest-to-smallest.
        assert parse_duration("1d30s") == 86400 + 30

    def test_case_insensitive(self):
        assert parse_duration("1H30M") == parse_duration("1h30m") == 5400
        assert parse_duration("1D2H3M4S") == parse_duration("1d2h3m4s")

    def test_leading_and_trailing_whitespace_ignored(self):
        assert parse_duration("  1h30m  ") == 5400

    def test_internal_whitespace_between_components(self):
        assert parse_duration("1h   30m") == 5400

    def test_bare_integer_means_seconds(self):
        assert parse_duration("45") == 45

    def test_bare_integer_with_surrounding_whitespace(self):
        assert parse_duration("  45  ") == 45

    def test_large_values(self):
        assert parse_duration("100d") == 100 * 86400
        assert parse_duration("9999s") == 9999


class TestParseErrors:
    @pytest.mark.parametrize("text", ["", "   ", "\t", "\n", "\n  \t"])
    def test_empty_or_whitespace_only(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize(
        "value", [None, 5, 5.0, [], {}, ("1h",), True, False]
    )
    def test_non_string_input(self, value):
        with pytest.raises(DurationError):
            parse_duration(value)

    @pytest.mark.parametrize("text", ["5w", "1y", "2x30m", "10min"])
    def test_unknown_unit(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize("text", ["1h2h", "1d2d", "5m5m", "1s1s"])
    def test_repeated_unit(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize("text", ["-5m", "-1h", "1h-30m"])
    def test_negative_value(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize("text", ["h", "d", "m", "s", "hms"])
    def test_bare_unit_no_number(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize(
        "text", ["1h30", "30h1", "1h30x", "1hh", "abc"]
    )
    def test_trailing_garbage(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)

    @pytest.mark.parametrize("text", ["30m1h", "1s1h", "1m1d"])
    def test_units_out_of_order(self, text):
        with pytest.raises(DurationError):
            parse_duration(text)


class TestFormatValid:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (5400, "1h30m"),
            (45, "45s"),
            (0, "0s"),
            (86400, "1d"),
            (3600, "1h"),
            (60, "1m"),
            (1, "1s"),
            (86400 + 3600, "1d1h"),
            (86400 + 30, "1d30s"),
            (90061, "1d1h1m1s"),
            (3601, "1h1s"),
        ],
    )
    def test_known_values(self, seconds, expected):
        assert format_duration(seconds) == expected

    def test_omits_zero_components(self):
        assert "0d" not in format_duration(3600)
        assert "0h" not in format_duration(60)
        assert "0m" not in format_duration(1)

    def test_zero_seconds_renders_as_0s(self):
        assert format_duration(0) == "0s"


class TestFormatErrors:
    @pytest.mark.parametrize("value", [-1, -100, -86400])
    def test_negative_raises(self, value):
        with pytest.raises(DurationError):
            format_duration(value)

    @pytest.mark.parametrize("value", [1.5, "60", None, [], {}, 5.0])
    def test_non_integer_raises(self, value):
        with pytest.raises(DurationError):
            format_duration(value)

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_is_not_accepted_as_int(self, value):
        with pytest.raises(DurationError):
            format_duration(value)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "n",
        [
            0, 1, 2, 30, 59, 60, 61, 119, 120,
            3599, 3600, 3601, 3661,
            86399, 86400, 86401,
            90061, 172800, 100000, 123456,
            999999, 604800,
        ],
    )
    def test_round_trip_specific_values(self, n):
        assert parse_duration(format_duration(n)) == n

    def test_round_trip_range(self):
        for n in range(0, 100_000, 37):
            assert parse_duration(format_duration(n)) == n

    def test_round_trip_random_large_values(self):
        rng = random.Random(12345)
        for _ in range(200):
            n = rng.randint(0, 10_000_000)
            assert parse_duration(format_duration(n)) == n
```