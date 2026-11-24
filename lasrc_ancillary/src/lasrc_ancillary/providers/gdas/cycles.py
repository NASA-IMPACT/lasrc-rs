"""GDAS cycle selection.

GDAS runs every 6 hours (00, 06, 12, 18 UTC). Each cycle is one instant for the whole globe, so
the cycles a granule needs depend only on its UTC acquisition time.
"""

import datetime as dt

from lasrc_ancillary.acquisition import to_utc

CYCLE = dt.timedelta(hours=6)


def gdas_cycles(acquisition_time: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """The GDAS cycle times at or before, and 6 hours after, acquisition_time (UTC)."""
    t = to_utc(acquisition_time)
    cycle1 = t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)
    return cycle1, cycle1 + CYCLE


def cycle_weights(
    acquisition_time: dt.datetime, cycles: tuple[dt.datetime, dt.datetime]
) -> tuple[float, float]:
    """Linear interpolation weights of the two cycles at acquisition_time."""
    t = to_utc(acquisition_time)
    t1, t2 = (to_utc(c) for c in cycles)
    if not t1 <= t <= t2 or t1 == t2:
        raise ValueError(f"{t.isoformat()} is not within the cycles {t1} to {t2}")

    w2 = (t - t1) / (t2 - t1)
    return 1.0 - w2, w2


def gdas_cycles_for_windows(
    windows: list[tuple[dt.datetime, dt.datetime]],
) -> list[dt.datetime]:
    """Every GDAS cycle needed by an acquisition anywhere in any of the windows."""
    cycles: set[dt.datetime] = set()
    for start, end in windows:
        cycle, last = gdas_cycles(start)[0], gdas_cycles(end)[1]
        while cycle <= last:
            cycles.add(cycle)
            cycle += CYCLE
    return sorted(cycles)
