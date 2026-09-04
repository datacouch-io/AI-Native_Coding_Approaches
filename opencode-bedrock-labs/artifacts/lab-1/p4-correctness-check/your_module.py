from datetime import datetime


def parse_iso8601(s: str) -> datetime:
    """Parse an ISO-8601 timestamp. Requires an explicit timezone (offset or 'Z')."""
    if not s or not isinstance(s, str):
        raise ValueError(f"invalid ISO-8601 timestamp: {s!r}")
    normalized = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError(f"invalid ISO-8601 timestamp: {s!r}") from e
    if dt.tzinfo is None:
        raise ValueError(f"timestamp missing timezone: {s!r}")
    return dt
