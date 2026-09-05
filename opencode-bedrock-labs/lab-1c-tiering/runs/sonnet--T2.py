import re
from typing import List, Optional, Tuple

_CORE_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
_IDENT_RE = re.compile(r'^[0-9A-Za-z-]+$')
_BUILD_RE = re.compile(r'^[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*$')


def _parse_semver(version: str) -> Tuple[Tuple[int, int, int], Optional[List[str]]]:
    if not isinstance(version, str) or version == "":
        raise ValueError(f"Invalid semver: {version!r}")

    # Strip build metadata (ignored entirely for comparison), but still
    # validate its basic shape so obviously malformed input is rejected.
    if '+' in version:
        main, build = version.split('+', 1)
        if not build or not _BUILD_RE.match(build):
            raise ValueError(f"Invalid build metadata: {version!r}")
    else:
        main = version

    # Extract optional pre-release suffix.
    if '-' in main:
        core, pre = main.split('-', 1)
        if not pre:
            raise ValueError(f"Invalid pre-release: {version!r}")
        pre_ids = pre.split('.')
        for pid in pre_ids:
            if not pid or not _IDENT_RE.match(pid):
                raise ValueError(f"Invalid pre-release identifier in: {version!r}")
            if pid.isdigit() and len(pid) > 1 and pid[0] == '0':
                raise ValueError(f"Invalid numeric identifier (leading zero): {version!r}")
    else:
        core = main
        pre_ids = None

    m = _CORE_RE.match(core)
    if not m:
        raise ValueError(f"Invalid version core: {version!r}")

    major, minor, patch = (int(x) for x in m.groups())
    return (major, minor, patch), pre_ids


def _compare_prerelease(a_ids: List[str], b_ids: List[str]) -> int:
    for ai, bi in zip(a_ids, b_ids):
        a_num = ai.isdigit()
        b_num = bi.isdigit()

        if a_num and b_num:
            av, bv = int(ai), int(bi)
            if av != bv:
                return -1 if av < bv else 1
            # equal, continue to next identifier
        elif a_num and not b_num:
            # numeric identifiers always rank lower than non-numeric ones
            return -1
        elif b_num and not a_num:
            return 1
        else:
            if ai != bi:
                return -1 if ai < bi else 1
            # equal, continue

    if len(a_ids) != len(b_ids):
        # the longer chain outranks its own prefix
        return -1 if len(a_ids) < len(b_ids) else 1
    return 0


def compare_semver(a: str, b: str) -> int:
    (a_core, a_pre) = _parse_semver(a)
    (b_core, b_pre) = _parse_semver(b)

    if a_core != b_core:
        return -1 if a_core < b_core else 1

    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None and b_pre is not None:
        # a has no pre-release (full release) -> higher
        return 1
    if a_pre is not None and b_pre is None:
        return -1

    # both have pre-release identifiers
    return _compare_prerelease(a_pre, b_pre)
