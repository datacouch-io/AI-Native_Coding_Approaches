"""Semantic version comparison.

Implements comparison of MAJOR.MINOR.PATCH versions with optional
pre-release identifiers and build metadata, following semver ordering rules.
"""

from typing import List, Optional, Tuple

_DIGITS = frozenset("0123456789")
_ALLOWED_ID = frozenset(
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "-"
)


def _is_numeric(s: str) -> bool:
    return len(s) > 0 and all(c in _DIGITS for c in s)


def _parse_number(s: str) -> int:
    """Parse a non-negative integer with no leading zeros."""
    if not _is_numeric(s):
        raise ValueError("invalid numeric component: {!r}".format(s))
    if len(s) > 1 and s[0] == "0":
        raise ValueError("leading zeros not allowed: {!r}".format(s))
    return int(s)


def _parse_prerelease(s: str) -> List[str]:
    """Validate and split a pre-release string into identifiers."""
    if s == "":
        raise ValueError("empty pre-release section")
    parts = s.split(".")
    for part in parts:
        if part == "":
            raise ValueError("empty pre-release identifier")
        if not all(c in _ALLOWED_ID for c in part):
            raise ValueError("invalid pre-release identifier: {!r}".format(part))
        if _is_numeric(part) and len(part) > 1 and part[0] == "0":
            raise ValueError(
                "numeric pre-release identifier with leading zeros: {!r}".format(part)
            )
    return parts


def _validate_build(s: str) -> None:
    if s == "":
        raise ValueError("empty build metadata section")
    parts = s.split(".")
    for part in parts:
        if part == "":
            raise ValueError("empty build metadata identifier")
        if not all(c in _ALLOWED_ID for c in part):
            raise ValueError("invalid build metadata identifier: {!r}".format(part))


def _parse(version: str) -> Tuple[int, int, int, Optional[List[str]]]:
    """Parse a semver string into (major, minor, patch, prerelease-or-None)."""
    if not isinstance(version, str):
        raise ValueError("version must be a string")

    rest = version

    # Build metadata: everything after the first '+'.
    plus = rest.find("+")
    if plus != -1:
        build = rest[plus + 1:]
        rest = rest[:plus]
        _validate_build(build)

    # Pre-release: everything after the first '-' in the remaining text.
    dash = rest.find("-")
    if dash != -1:
        pre_str = rest[dash + 1:]
        rest = rest[:dash]
        prerelease: Optional[List[str]] = _parse_prerelease(pre_str)
    else:
        prerelease = None

    core = rest.split(".")
    if len(core) != 3:
        raise ValueError("version core must be MAJOR.MINOR.PATCH: {!r}".format(version))

    major = _parse_number(core[0])
    minor = _parse_number(core[1])
    patch = _parse_number(core[2])

    return major, minor, patch, prerelease


def _cmp_int(x: int, y: int) -> int:
    if x < y:
        return -1
    if x > y:
        return 1
    return 0


def _cmp_identifier(x: str, y: str) -> int:
    x_num = _is_numeric(x)
    y_num = _is_numeric(y)
    if x_num and y_num:
        return _cmp_int(int(x), int(y))
    if x_num:
        return -1
    if y_num:
        return 1
    if x < y:
        return -1
    if x > y:
        return 1
    return 0


def _cmp_prerelease(x: List[str], y: List[str]) -> int:
    for xi, yi in zip(x, y):
        result = _cmp_identifier(xi, yi)
        if result != 0:
            return result
    return _cmp_int(len(x), len(y))


def compare_semver(a: str, b: str) -> int:
    """Compare two semantic version strings.

    Returns -1 if a < b, 0 if they are equal in precedence, 1 if a > b.
    Build metadata is ignored. Malformed input raises ValueError.
    """
    a_major, a_minor, a_patch, a_pre = _parse(a)
    b_major, b_minor, b_patch, b_pre = _parse(b)

    for x, y in (
        (a_major, b_major),
        (a_minor, b_minor),
        (a_patch, b_patch),
    ):
        result = _cmp_int(x, y)
        if result != 0:
            return result

    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:
        return 1
    if b_pre is None:
        return -1

    return _cmp_prerelease(a_pre, b_pre)
