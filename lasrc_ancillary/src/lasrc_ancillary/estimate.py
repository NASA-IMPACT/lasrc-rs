"""Estimate a granule's acquisition time from its date and scene or tile center.

The orchestration only has the granule ID: a Landsat product ID has the UTC date but no time, and
a Sentinel-2 product name has the datatake start rather than the tile's sensing time. Landsat 8/9
and Sentinel-2 are sun-synchronous, so the local mean solar time at a point follows from the
orbit's inclination, its descending node time and the point's latitude.

The estimate only decides when to look for GDAS files. The processing job uses the exact time.
"""

import datetime as dt
import math
from dataclasses import dataclass

from lasrc_ancillary.cycles import CYCLE, gdas_cycles, to_utc


@dataclass(frozen=True)
class Orbit:
    """A sun-synchronous orbit, enough to estimate when it passes over a point."""

    inclination: float
    """Orbit inclination, in degrees."""
    descending_node_time: float
    """Local mean solar time at the descending equator crossing, in hours."""


# Landsat 8 is nominally 10:00, but crossed at about 10:12 in 2019-2020 scenes.
PLATFORMS: dict[str, Orbit] = {
    "LANDSAT_8": Orbit(inclination=98.2, descending_node_time=10.2),
    "LANDSAT_9": Orbit(inclination=98.2, descending_node_time=10.2),
    "SENTINEL_2": Orbit(inclination=98.62, descending_node_time=10.5),
}


DEGREES_PER_HOUR = 15.0


def _orbit(platform: str) -> Orbit:
    try:
        return PLATFORMS[platform]
    except KeyError:
        raise ValueError(
            f"unknown platform {platform!r}, expected one of {list(PLATFORMS)}"
        ) from None


def _local_solar_time(orbit: Orbit, lat: float) -> float:
    """Local mean solar time, in hours, when a descending pass reaches latitude ``lat``.

    The pass crosses the equator at the orbit's descending node time. Away from the equator the
    ground track has turned in longitude relative to the node, which shifts the local time (by
    about 20 minutes at 30 degrees latitude and an hour at 60).
    """
    inclination = math.radians(orbit.inclination)
    sin_lat = math.sin(math.radians(lat))
    # Angle along the orbit from the ascending node, on the descending half of the orbit.
    along_orbit = math.pi - math.asin(
        max(-1.0, min(1.0, sin_lat / math.sin(inclination)))
    )
    # Longitude of that point relative to the descending node.
    from_node = math.atan2(
        math.cos(inclination) * math.sin(along_orbit), math.cos(along_orbit)
    )
    from_node_deg = (math.degrees(from_node - math.pi) + 180.0) % 360.0 - 180.0
    return orbit.descending_node_time + from_node_deg / DEGREES_PER_HOUR


def estimate_acquisition_time(
    platform: str, day: dt.date, lat: float, lon: float
) -> dt.datetime:
    """Estimated UTC acquisition time on the UTC date ``day`` at (lat, lon) in degrees."""
    local_time = _local_solar_time(_orbit(platform), lat)
    utc_hours = (local_time - lon / DEGREES_PER_HOUR) % 24.0
    midnight = dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC)
    return midnight + dt.timedelta(hours=utc_hours)


def estimate_acquisition_windows(
    platform: str,
    day: dt.date,
    lat: float,
    lon: float,
    not_before: dt.datetime | None = None,
    margin: dt.timedelta = dt.timedelta(minutes=30),
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Time windows that contain the acquisition, from the estimate plus or minus ``margin``.

    The acquisition is on the UTC date ``day`` (Landsat), or within 24 hours after
    ``not_before`` (Sentinel-2, whose product name gives the datatake start). The estimate is a
    time of day, so near 00:00 UTC the margin wraps to the other end of that range, and the
    result can be two windows.
    """
    t = estimate_acquisition_time(platform, day, lat, lon)
    if not_before is None:
        low = dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC)
    else:
        low = to_utc(not_before)
    high = low + dt.timedelta(days=1) - dt.timedelta(microseconds=1)
    windows = []
    for days in (-1, 0, 1):
        candidate = t + dt.timedelta(days=days)
        start = max(candidate - margin, low)
        end = min(candidate + margin, high)
        if start <= end:
            windows.append((start, end))
    return windows


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
