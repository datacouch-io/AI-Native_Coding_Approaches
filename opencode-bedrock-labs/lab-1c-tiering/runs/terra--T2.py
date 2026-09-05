import re


_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z-]+$")


def _parse(version: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None]:
    if not isinstance(version, str):
        raise ValueError("version must be a string")

    if version.count("+") > 1:
        raise ValueError("invalid build metadata")

    main, separator, build = version.partition("+")
    if separator:
        if not build or any(
            not identifier or not _IDENTIFIER_RE.fullmatch(identifier)
            for identifier in build.split(".")
        ):
            raise ValueError("invalid build metadata")

    if main.count("-") > 1:
        raise ValueError("invalid pre-release suffix")

    core, separator, prerelease = main.partition("-")
    match = _CORE_RE.fullmatch(core)
    if not match:
        raise ValueError("invalid version core")

    if separator:
        identifiers = prerelease.split(".")
        if not prerelease or any(
            not identifier
            or not _IDENTIFIER_RE.fullmatch(identifier)
            or (identifier.isdigit() and len(identifier) > 1 and identifier[0] == "0")
            for identifier in identifiers
        ):
            raise ValueError("invalid pre-release suffix")
        parsed_prerelease = tuple(identifiers)
    else:
        parsed_prerelease = None

    return tuple(map(int, match.groups())), parsed_prerelease


def compare_semver(a: str, b: str) -> int:
    core_a, prerelease_a = _parse(a)
    core_b, prerelease_b = _parse(b)

    if core_a != core_b:
        return -1 if core_a < core_b else 1

    if prerelease_a is None and prerelease_b is None:
        return 0
    if prerelease_a is None:
        return 1
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

    if len(prerelease_a) == len(prerelease_b):
        return 0
    return -1 if len(prerelease_a) < len(prerelease_b) else 1
