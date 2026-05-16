from datetime import datetime, timedelta

# Beijing timezone offset = UTC+8
BEIJING_OFFSET = timedelta(hours=8)


def now() -> datetime:
    """Return current Beijing time (UTC+8) as a naive datetime."""
    return datetime.utcnow() + BEIJING_OFFSET
