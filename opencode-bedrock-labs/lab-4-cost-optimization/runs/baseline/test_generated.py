"""Tests for the ``durations`` module.

The suite is written against the published specification: parsing of compound
duration strings, compact formatting, the documented error cases, and the
round-trip property ``parse_duration(format_duration(n)) == n``.
"""

import random

import pytest

from durations import DurationError, format_duration, parse_duration


DAY = 86_400
HOUR = 3_600
MINUTE = 60


# --------------------------------------------------------------------------
# DurationError
# --------------------------------------------------------------------------

def test_duration_error_is_a_value_error():
    assert issubclass(DurationError, ValueError)


def test_duration_error_can_be_caught_as_value_error():
    with pytest.raises(ValueError):
        parse_duration("")


# --------------------------------------------------------------------------
# parse_duration: happy path (contract 1, 2, 3)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # single components
        ("1s", 1),
        ("0s", 0),
        ("45s", 45),
        ("90s", 90),
        ("1m", MINUTE),
        ("30m", 30 * MINUTE),
        ("1h", HOUR),
        ("24h", 24 * HOUR),
        ("1d", DAY),
        ("2d", 2 * DAY),
        # compound, contiguous
        ("1h30m", HOUR + 30 * MINUTE),
        ("2d4h", 2 * DAY + 4 * HOUR),
        ("1m30s", 90),
        ("1h1m1s", HOUR + MINUTE + 1),
        ("1d1h1m1s", DAY + HOUR + MINUTE + 1),
        # compound, space separated
        ("1h 30m", HOUR + 30 * MINUTE),
        ("2d 4h", 2 * DAY + 4 * HOUR),
        ("1d 1h 1m 1s", DAY + HOUR + MINUTE + 1),
        # compound, non-contiguous units (contract 2)
        ("1d 30s", DAY + 30),
        ("1d30s", DAY + 30),
        ("1h5s", HOUR + 5),
        ("2d15m", 2 * DAY + 15 * MINUTE),
        ("1d 2m", DAY + 2 * MINUTE),
        # explicit zero components are allowed
        ("0h0m0s", 0),
        ("0d0h0m0s", 0),
        ("1h0m0s", HOUR),
        # large values
        ("100d", 100 * DAY),
        ("999s", 999),
        ("48h", 48 * HOUR),
    ],
)
def test_parse_duration_returns_expected_seconds(text, expected):
    assert parse_duration(text) == expected


def test_parse_duration_returns_an_int():
    result = parse_duration("1h30m")
    assert isinstance(result, int)
    assert not isinstance(result, bool)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("1", 1),
        ("45", 45),
        ("90", 90),
        ("3600", HOUR),
        ("86400", DAY),
        ("000045", 45),
    ],
)
def test_parse_duration_bare_integer_means_seconds(text, expected):
    """Contract 3: a bare integer with no unit is a count of seconds."""
    assert parse_duration(text) == expected


def test_parse_duration_bare_integer_matches_explicit_seconds():
    assert parse_duration("45") == parse_duration("45s")


# --------------------------------------------------------------------------
# parse_duration: case insensitivity (contract 4)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("upper", "lower"),
    [
        ("1H30M", "1h30m"),
        ("1H 30M", "1h 30m"),
        ("2D4H", "2d4h"),
        ("45S", "45s"),
        ("1D", "1d"),
        ("1d1H1m1S", "1d1h1m1s"),
        ("1D 30S", "1d 30s"),
    ],
)
def test_parse_duration_is_case_insensitive(upper, lower):
    assert parse_duration(upper) == parse_duration(lower)


def test_parse_duration_mixed_case_value():
    assert parse_duration("1H30M") == HOUR + 30 * MINUTE


# --------------------------------------------------------------------------
# parse_duration: surrounding whitespace (contract 5)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        " 1h30m",
        "1h30m ",
        "   1h30m   ",
        "\t1h30m\n",
        "\n 1h 30m \t",
    ],
)
def test_parse_duration_ignores_surrounding_whitespace(text):
    assert parse_duration(text) == HOUR + 30 * MINUTE


def test_parse_duration_ignores_whitespace_around_bare_integer():
    assert parse_duration("  45  ") == 45


# --------------------------------------------------------------------------
# parse_duration: errors (contract 6)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_parse_duration_rejects_empty_or_whitespace_only(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    "value",
    [
        None,
        5,
        0,
        5.0,
        True,
        [],
        ["1h"],
        ("1h",),
        {"1h": 1},
        b"1h30m",
        bytearray(b"1h"),
        object(),
    ],
)
def test_parse_duration_rejects_non_string_input(value):
    with pytest.raises(DurationError):
        parse_duration(value)


@pytest.mark.parametrize(
    "text",
    [
        "5w",
        "5W",
        "10y",
        "3x",
        "1q",
        "1h30x",
        "1d5w",
        "5ms",
        "1hh",
    ],
)
def test_parse_duration_rejects_unknown_units(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "1h2h",
        "1h 2h",
        "5m5m",
        "1d1d",
        "1s1s",
        "1h30m30m",
        "1d1h1h",
    ],
)
def test_parse_duration_rejects_repeated_units(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "-5m",
        "-1h",
        "-45",
        "-0s",
        " -5m ",
        "+5m",
        "+45",
    ],
)
def test_parse_duration_rejects_signed_or_negative_values(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "h",
        "s",
        "m",
        "d",
        "hm",
        "h30m",
        "m d",
        "1h m",
        "1d h",
    ],
)
def test_parse_duration_rejects_bare_unit_without_number(text):
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "1h30",           # trailing number with no unit (contract 6)
        "1h30m5",
        "1d 1h 1m 1",
        "1h abc",
        "abc",
        "1h,30m",
        "1h:30m",
        "1h-30m",
        "1h+30m",
        "1.5h",
        "1,5h",
        "30 45",
        "1h 30m junk",
        "(1h)",
        "1h/30m",
    ],
)
def test_parse_duration_rejects_trailing_or_embedded_garbage(text):
    with pytest.raises(DurationError):
        parse_duration(text)


def test_parse_duration_error_message_is_non_empty():
    with pytest.raises(DurationError) as excinfo:
        parse_duration("5w")
    assert str(excinfo.value)


# --------------------------------------------------------------------------
# format_duration: happy path (contract 7)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (1, "1s"),
        (45, "45s"),
        (59, "59s"),
        (60, "1m"),
        (90, "1m30s"),
        (599, "9m59s"),
        (3600, "1h"),
        (5400, "1h30m"),
        (3661, "1h1m1s"),
        (86400, "1d"),
        (86399, "23h59m59s"),
        (86430, "1d30s"),
        (90061, "1d1h1m1s"),
        (172800, "2d"),
        (187200, "2d4h"),
        (DAY + 2 * MINUTE, "1d2m"),
    ],
)
def test_format_duration_renders_compact_form(seconds, expected):
    assert format_duration(seconds) == expected


def test_format_duration_returns_a_string():
    assert isinstance(format_duration(5400), str)


@pytest.mark.parametrize("seconds", [0, 1, 60, 5400, 86400, 90061, 987_654])
def test_format_duration_output_contains_no_whitespace(seconds):
    assert " " not in format_duration(seconds)
    assert format_duration(seconds) == format_duration(seconds).strip()


@pytest.mark.parametrize(
    ("seconds", "absent_unit"),
    [
        (5400, "s"),      # 1h30m has no seconds component
        (86400, "h"),     # 1d has no hours component
        (86430, "m"),     # 1d30s has no minutes component
        (45, "m"),
        (45, "h"),
        (45, "d"),
    ],
)
def test_format_duration_omits_zero_components(seconds, absent_unit):
    assert absent_unit not in format_duration(seconds)


@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 3599, 3600, 86399, 86400, 123_456])
def test_format_duration_orders_units_largest_first(seconds):
    text = format_duration(seconds)
    positions = [text.index(u) for u in "dhms" if u in text]
    assert positions == sorted(positions)


# --------------------------------------------------------------------------
# format_duration: errors (contract 8)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("seconds", [-1, -45, -60, -3600, -86400])
def test_format_duration_rejects_negative_values(seconds):
    with pytest.raises(DurationError):
        format_duration(seconds)


@pytest.mark.parametrize(
    "value",
    [
        1.5,
        0.0,
        60.0,
        -1.5,
        "60",
        "1h",
        None,
        [],
        [60],
        (60,),
        {"seconds": 60},
        object(),
        complex(1, 0),
    ],
)
def test_format_duration_rejects_non_integer_input(value):
    with pytest.raises(DurationError):
        format_duration(value)


def test_format_duration_error_message_is_non_empty():
    with pytest.raises(DurationError) as excinfo:
        format_duration(-1)
    assert str(excinfo.value)


# --------------------------------------------------------------------------
# Round-trip property (contract 9)
# --------------------------------------------------------------------------

_EDGE_SECONDS = [
    0,
    1,
    2,
    59,
    60,
    61,
    119,
    120,
    3599,
    3600,
    3601,
    3660,
    3661,
    5400,
    86_399,
    86_400,
    86_401,
    86_430,
    90_061,
    172_800,
    187_200,
    1_000_000,
    123_456_789,
]


@pytest.mark.parametrize("seconds", _EDGE_SECONDS)
def test_round_trip_edge_values(seconds):
    assert parse_duration(format_duration(seconds)) == seconds


@pytest.mark.parametrize("seconds", list(range(0, 200)))
def test_round_trip_small_values_exhaustively(seconds):
    assert parse_duration(format_duration(seconds)) == seconds


def test_round_trip_dense_sweep_across_unit_boundaries():
    candidates = set()
    for boundary in (0, MINUTE, HOUR, DAY, 7 * DAY, 365 * DAY):
        for delta in range(-3, 4):
            value = boundary + delta
            if value >= 0:
                candidates.add(value)
    for seconds in sorted(candidates):
        assert parse_duration(format_duration(seconds)) == seconds


def test_round_trip_randomised_values():
    rng = random.Random(20260905)
    for _ in range(2_000):
        seconds = rng.randrange(0, 400 * DAY)
        rendered = format_duration(seconds)
        assert parse_duration(rendered) == seconds, rendered


@pytest.mark.parametrize(
    "text",
    [
        "0s",
        "1s",
        "45s",
        "1m",
        "1m30s",
        "1h",
        "1h30m",
        "1h1m1s",
        "1d",
        "1d30s",
        "2d4h",
        "1d1h1m1s",
        "23h59m59s",
    ],
)
def test_format_round_trips_canonical_strings(text):
    """Canonical (compact) strings survive parse -> format unchanged."""
    assert format_duration(parse_duration(text)) == text


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("45", "45s"),
        ("90s", "1m30s"),
        ("1h 30m", "1h30m"),
        ("1H30M", "1h30m"),
        ("  2d4h ", "2d4h"),
        ("0h0m0s", "0s"),
        ("60s", "1m"),
        ("24h", "1d"),
        ("1440m", "1d"),
    ],
)
def test_non_canonical_input_normalises_to_canonical_output(text, canonical):
    assert format_duration(parse_duration(text)) == canonical
