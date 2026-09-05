"""Reference solutions - prove each suite is satisfiable. Never shown to models."""
import re

# ---- T1 ---------------------------------------------------------------------
def chunk(seq, size):
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")
    return [list(seq[i:i + size]) for i in range(0, len(seq), size)]


# ---- T2 ---------------------------------------------------------------------
_CORE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_NUMERIC = re.compile(r"^\d+$")


def _parse(v):
    if not isinstance(v, str) or not v:
        raise ValueError(f"malformed version: {v!r}")
    v = v.split("+", 1)[0]                      # build metadata is ignored
    core, _, pre = v.partition("-")
    m = _CORE.match(core)
    if not m:
        raise ValueError(f"malformed version: {v!r}")
    nums = tuple(int(g) for g in m.groups())
    if pre == "" and "-" in v:
        raise ValueError(f"empty pre-release: {v!r}")
    ids = pre.split(".") if pre else []
    for i in ids:
        if not i or (not _NUMERIC.match(i) and not re.match(r"^[0-9A-Za-z-]+$", i)):
            raise ValueError(f"malformed pre-release: {v!r}")
        if _NUMERIC.match(i) and len(i) > 1 and i[0] == "0":
            raise ValueError(f"leading zero in pre-release: {v!r}")
    return nums, ids


def _cmp(a, b):
    return (a > b) - (a < b)


def compare_semver(a, b):
    (an, ap), (bn, bp) = _parse(a), _parse(b)
    if an != bn:
        return _cmp(an, bn)
    if not ap and not bp:
        return 0
    if not ap:
        return 1                                 # release outranks pre-release
    if not bp:
        return -1
    for x, y in zip(ap, bp):
        xn, yn = bool(_NUMERIC.match(x)), bool(_NUMERIC.match(y))
        if xn and yn:
            if int(x) != int(y):
                return _cmp(int(x), int(y))
        elif xn != yn:
            return -1 if xn else 1               # numeric ranks below alphanumeric
        elif x != y:
            return _cmp(x, y)
    return _cmp(len(ap), len(bp))                # longer chain outranks its prefix


# ---- T3 ---------------------------------------------------------------------
def backoff_schedule(attempts, base, factor, cap, max_elapsed):
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise ValueError("attempts must be a non-negative integer")
    for name, val in (("base", base), ("factor", factor),
                      ("cap", cap), ("max_elapsed", max_elapsed)):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
            raise ValueError(f"{name} must be a non-negative number")

    out, elapsed = [], 0.0
    for i in range(attempts):
        delay = min(base * (factor ** i), cap)
        remaining = max_elapsed - elapsed
        if remaining <= 0:
            break
        if elapsed + delay > max_elapsed:
            delay = remaining
            if round(delay, 3) == 0:
                break
            out.append(round(delay, 3))
            break
        out.append(round(delay, 3))
        elapsed += delay
    return out
