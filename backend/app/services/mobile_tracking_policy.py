"""Pure work-session rules shared by mobile endpoints and regression tests."""
from datetime import datetime, timedelta, timezone

MAX_SHIFT = timedelta(hours=24)
MAX_UPLOAD_AGE = timedelta(hours=24)


def utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def session_state(record, now):
    now = utc(now)
    start, end = utc(record.get("check_in_at")), utc(record.get("check_out_at"))
    until = start + MAX_SHIFT if start else None
    return {
        **record,
        "active": bool(start and not end and start <= now < until),
        "requires_review": bool(start and not end and now >= until),
        "tracking_until": until,
        "server_time": now,
    }


def point_in_shift(record, captured, now):
    """Allow delayed delivery, never an off-shift capture; clock skew fails closed."""
    captured, now = utc(captured), utc(now)
    start, end = utc(record.get("check_in_at")), utc(record.get("check_out_at"))
    if not start or captured is None:
        return False
    ceiling = min(end, start + MAX_SHIFT) if end else start + MAX_SHIFT
    return start <= captured <= ceiling and now - MAX_UPLOAD_AGE <= captured <= now + timedelta(seconds=30)
