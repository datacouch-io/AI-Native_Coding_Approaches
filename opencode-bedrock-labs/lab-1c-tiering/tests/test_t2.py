"""T2 acceptance - hidden from every model."""
import pytest
from solution import compare_semver


@pytest.mark.parametrize("a,b,expected", [
    ("1.0.0", "1.0.0", 0),
    ("2.0.0", "1.9.9", 1),
    ("1.2.0", "1.10.0", -1),
    ("1.0.1", "1.0.0", 1),
    ("0.0.1", "0.1.0", -1),
])
def test_numeric_precedence(a, b, expected):
    assert compare_semver(a, b) == expected

def test_prerelease_is_lower_than_release():
    assert compare_semver("1.0.0-alpha", "1.0.0") == -1
    assert compare_semver("1.0.0", "1.0.0-alpha") == 1

@pytest.mark.parametrize("a,b,expected", [
    ("1.0.0-alpha", "1.0.0-alpha.1", -1),
    ("1.0.0-alpha.1", "1.0.0-alpha.beta", -1),
    ("1.0.0-alpha.beta", "1.0.0-beta", -1),
    ("1.0.0-beta.2", "1.0.0-beta.11", -1),
    ("1.0.0-rc.1", "1.0.0", -1),
])
def test_prerelease_ordering(a, b, expected):
    assert compare_semver(a, b) == expected

def test_numeric_identifier_ranks_below_alphanumeric():
    assert compare_semver("1.0.0-1", "1.0.0-alpha") == -1

def test_build_metadata_ignored():
    assert compare_semver("1.0.0+build.5", "1.0.0") == 0
    assert compare_semver("1.0.0-alpha+x", "1.0.0-alpha+y") == 0

@pytest.mark.parametrize("bad", ["1.0", "1.0.0.0", "a.b.c", "", "01.0.0", "1.0.-1", None])
def test_malformed_raises(bad):
    with pytest.raises(ValueError):
        compare_semver(bad, "1.0.0")
