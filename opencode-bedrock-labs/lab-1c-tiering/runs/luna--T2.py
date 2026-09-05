import re


_VERSION_RE = re.compile(
    r"^([0-9]+)\.([0-9]+)\.([0-9]+)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def compare_semver(a: str, b: str) -> int:
    def parse(version: str) -> tuple[tuple[int, int, int], list[str] | None]:
        if not isinstance(version, str):
            raise ValueError("version must be a string")

        match = _VERSION_RE.fullmatch(version)
        if match is None:
            raise ValueError("malformed semantic version")

        major, minor, patch = match.group(1, 2, 3)
        if any(len(part) > 1 and part.startswith("0") for part in (major, minor, patch)):
            raise ValueError("version numbers must not have leading zeros")

        prerelease = match.group(4)
        identifiers = prerelease.split(".") if prerelease is not None else None

        if identifiers is not None:
            for identifier in identifiers:
                if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                    raise ValueError("numeric pre-release identifiers must not have leading zeros")

        return (int(major), int(minor), int(patch)), identifiers

    core_a, pre_a = parse(a)
    core_b, pre_b = parse(b)

    if core_a < core_b:
        return -1
    if core_a > core_b:
        return 1

    if pre_a is None and pre_b is None:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1

    for identifier_a, identifier_b in zip(pre_a, pre_b):
        numeric_a = identifier_a.isdigit()
        numeric_b = identifier_b.isdigit()

        if numeric_a and numeric_b:
            value_a = int(identifier_a)
            value_b = int(identifier_b)
            if value_a < value_b:
                return -1
            if value_a > value_b:
                return 1
        elif numeric_a != numeric_b:
            return -1 if numeric_a else 1
        elif identifier_a < identifier_b:
            return -1
        elif identifier_a > identifier_b:
            return 1

    if len(pre_a) < len(pre_b):
        return -1
    if len(pre_a) > len(pre_b):
        return 1
    return 0
