"""Fixed acceptance suite. Written by the lab, never shown to any model.

This is the constant against which every pipeline configuration is judged. A
cheaper pipeline is only cheaper if this still passes.
"""
import pytest

from durations import DurationError, format_duration, parse_duration


class TestParse:
    @pytest.mark.parametrize("text,seconds", [
        ("45", 45), ("90s", 90), ("30m", 1800), ("2h", 7200), ("1d", 86400),
        ("1h30m", 5400), ("1h 30m", 5400), ("2d4h", 187200), ("1d 30s", 86430),
        ("1d2h3m4s", 93784), ("0s", 0), ("0", 0),
    ])
    def test_valid_forms(self, text, seconds):
        assert parse_duration(text) == seconds

    def test_case_insensitive(self):
        assert parse_duration("1H30M") == parse_duration("1h30m") == 5400

    def test_surrounding_whitespace_ignored(self):
        assert parse_duration("  1h30m  ") == 5400

    @pytest.mark.parametrize("bad", [
        "", "   ", "5w", "1h2h", "-5m", "h", "1h30", "abc", "1.5h", "m30",
    ])
    def test_invalid_raises(self, bad):
        with pytest.raises(DurationError):
            parse_duration(bad)

    @pytest.mark.parametrize("bad", [None, 90, 1.5, [], {}])
    def test_non_string_raises(self, bad):
        with pytest.raises(DurationError):
            parse_duration(bad)


class TestFormat:
    @pytest.mark.parametrize("seconds,text", [
        (0, "0s"), (45, "45s"), (90, "1m30s"), (1800, "30m"), (5400, "1h30m"),
        (7200, "2h"), (86400, "1d"), (93784, "1d2h3m4s"), (187200, "2d4h"),
    ])
    def test_renders_compactly(self, seconds, text):
        assert format_duration(seconds) == text

    @pytest.mark.parametrize("bad", [-1, -3600, 1.5, "60", None])
    def test_invalid_raises(self, bad):
        with pytest.raises(DurationError):
            format_duration(bad)


class TestRoundTrip:
    @pytest.mark.parametrize("n", [0, 1, 59, 60, 61, 3599, 3600, 3601,
                                   86399, 86400, 86401, 93784, 1234567])
    def test_parse_of_format_is_identity(self, n):
        assert parse_duration(format_duration(n)) == n
