import re


_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _parse_semver(version: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None]:
    if not isinstance(version, str):
        raise ValueError("version must be a string")

    match = _SEMVER_RE.fullmatch(version)
    if match is None:
        raise ValueError(f"malformed semantic version: {version!r}")

    core = tuple(int(part) for part in match.group(1, 2, 3))
    prerelease = match.group(4)
    identifiers = tuple(prerelease.split(".")) if prerelease is not None else None
    return core, identifiers


def compare_semver(a: str, b: str) -> int:
    core_a, prerelease_a = _parse_semver(a)
    core_b, prerelease_b = _parse_semver(b)

    if core_a < core_b:
        return -1
    if core_a > core_b:
        return 1

    if prerelease_a is None:
        return 0 if prerelease_b is None else 1
    if prerelease_b is None:
        return -1

    for identifier_a, identifier_b in zip(prerelease_a, prerelease_b):
        if identifier_a == identifier_b:
            continue

        numeric_a = identifier_a.isdigit()
        numeric_b = identifier_b.isdigit()

        if numeric_a and numeric_b:
            return -1 if int(identifier_a) < int(identifier_b) else 1
        if numeric_a != numeric_b:
            return -1 if numeric_a else 1
        return -1 if identifier_a < identifier_b else 1

    if len(prerelease_a) < len(prerelease_b):
        return -1
    if len(prerelease_a) > len(prerelease_b):
        return 1
    return 0
