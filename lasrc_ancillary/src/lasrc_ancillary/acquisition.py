"""Acquisition time of a granule: exact from its metadata, or estimated from its granule ID.

The processing job reads the exact time from the Landsat or Sentinel-2 metadata. The orchestration
only has the granule ID: a Landsat product ID has the UTC date but no time, and a Sentinel-2
product name has the datatake start rather than the tile's sensing time. Landsat 8/9 and
Sentinel-2 are sun-synchronous, so the local mean solar time at a point follows from the orbit's
inclination, its descending node time and the point's latitude. The estimate only decides when to
look for ancillary data, never which data a granule uses.

Standard library only, so the orchestration can run it in a Lambda.
"""

import datetime as dt
import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


def to_utc(t: dt.datetime) -> dt.datetime:
    """Return ``t`` in UTC. Naive datetimes are rejected."""
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"datetime must be timezone-aware (UTC), got naive {t!r}")

    return t.astimezone(dt.UTC)


def read_acquisition_time(path: Path) -> dt.datetime:
    """UTC acquisition time from a Landsat MTL (``*_MTL.txt``) or a Sentinel-2 ``MTD_TL.xml``.

    Sentinel-2 uses the tile's ``SENSING_TIME``. ``PRODUCT_START_TIME`` in ``MTD_MSIL1C.xml`` is
    the start of the whole datatake, which can be many minutes earlier.
    """
    path = Path(path)
    if path.name.endswith("_MTL.txt"):
        return _landsat_mtl_time(path)
    if path.suffix.lower() == ".xml":
        return _sentinel_tile_time(path)
    raise ValueError(
        f"{path.name}: expected a Landsat *_MTL.txt or a Sentinel-2 MTD_TL.xml"
    )


def _landsat_mtl_time(path: Path) -> dt.datetime:
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    for name in ("DATE_ACQUIRED", "SCENE_CENTER_TIME"):
        if name not in fields:
            raise ValueError(f"{path.name}: missing {name}")
    m = re.fullmatch(
        r"(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?Z", fields["SCENE_CENTER_TIME"]
    )
    if m is None:
        raise ValueError(
            f"{path.name}: unexpected SCENE_CENTER_TIME {fields['SCENE_CENTER_TIME']}"
        )

    hh, mm, ss, frac = m.groups()
    day = dt.datetime.strptime(fields["DATE_ACQUIRED"], "%Y-%m-%d")
    micro = int((frac or "0")[:6].ljust(6, "0"))
    return day.replace(
        hour=int(hh), minute=int(mm), second=int(ss), microsecond=micro, tzinfo=dt.UTC
    )


def _sentinel_tile_time(path: Path) -> dt.datetime:
    root = ElementTree.parse(path).getroot()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "SENSING_TIME" and element.text:
            return dt.datetime.fromisoformat(element.text.strip()).astimezone(dt.UTC)
    raise ValueError(f"{path.name}: missing SENSING_TIME")


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
