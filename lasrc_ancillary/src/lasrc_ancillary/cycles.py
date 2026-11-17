"""GDAS cycle selection.

GDAS runs every 6 hours (00, 06, 12, 18 UTC). Each cycle is one instant for the whole globe, so
the cycles a granule needs depend only on its UTC acquisition time.
"""

import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

CYCLE = timedelta(hours=6)


def to_utc(t: datetime) -> datetime:
    """Return ``t`` in UTC. Naive datetimes are rejected."""
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"datetime must be timezone-aware (UTC), got naive {t!r}")
    return t.astimezone(UTC)


def parse_iso(text: str) -> datetime:
    """Parse an ISO 8601 date and time, accepting a trailing ``Z`` and any number of fraction
    digits (truncated to microseconds). Python 3.10's ``fromisoformat`` accepts neither.
    A time without a timezone stays naive.
    """
    s = text.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$", s)
    if m:
        s = f"{m.group(1)}.{m.group(2)[:6].ljust(6, '0')}{m.group(3)}"
    t = datetime.fromisoformat(s)
    return t if t.tzinfo is None else t.astimezone(UTC)


def gdas_cycles(acquisition_time: datetime) -> tuple[datetime, datetime]:
    """The GDAS cycle times at or before, and 6 hours after, acquisition_time (UTC)."""
    t = to_utc(acquisition_time)
    cycle1 = t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)
    return cycle1, cycle1 + CYCLE


def cycle_weights(
    acquisition_time: datetime, cycles: tuple[datetime, datetime]
) -> tuple[float, float]:
    """Linear interpolation weights of the two cycles at acquisition_time."""
    t = to_utc(acquisition_time)
    t1, t2 = (to_utc(c) for c in cycles)
    if not t1 <= t <= t2 or t1 == t2:
        raise ValueError(f"{t.isoformat()} is not within the cycles {t1} to {t2}")
    w2 = (t - t1) / (t2 - t1)
    return 1.0 - w2, w2
