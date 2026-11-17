import datetime as dt

import pytest
from lasrc_ancillary.estimate import (
    estimate_acquisition_time,
    estimate_acquisition_windows,
    gdas_cycles_for_windows,
)


def iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def covers(windows, t):
    return any(s <= t <= e for s, e in windows)


def test_landsat8_austin():
    # LC08 027039, 2019-09-01, scene center 30.3N 97.8W, SCENE_CENTER_TIME 17:03:12
    t = estimate_acquisition_time("LANDSAT_8", dt.date(2019, 9, 1), 30.3, -97.8)
    assert abs((t - iso("2019-09-01T17:03:12Z")).total_seconds()) < 60


def test_landsat8_patagonia():
    # LC08 231089, 2020-08-07, scene center 41.8S 70.2W, SCENE_CENTER_TIME 14:23:41
    t = estimate_acquisition_time("LANDSAT_8", dt.date(2020, 8, 7), -41.8, -70.2)
    assert abs((t - iso("2020-08-07T14:23:41Z")).total_seconds()) < 60


@pytest.mark.parametrize(
    ("platform", "lat", "lon"),
    [
        ("SENTINEL_2", -27.5, 153.0),  # Brisbane, estimate about 23:59:53
        ("SENTINEL_2", 0.0, 157.0),  # estimate about 00:02
        ("LANDSAT_8", -37.8, 145.0),  # Melbourne, estimate about 00:06
        ("LANDSAT_8", -33.9, 151.2),  # Sydney, estimate about 23:45
    ],
)
def test_near_midnight_both_ends_of_the_day_are_covered(platform, lat, lon):
    day = dt.date(2026, 3, 14)
    windows = estimate_acquisition_windows(platform, day, lat, lon)
    # a true time a few minutes either side of 00:00 must be covered on this UTC date
    assert covers(windows, iso("2026-03-14T00:03:00Z"))
    assert covers(windows, iso("2026-03-14T23:57:00Z"))
    cycles = gdas_cycles_for_windows(windows)
    assert iso("2026-03-14T06:00Z") in cycles and iso("2026-03-15T00:00Z") in cycles


def test_date_line_wellington():
    # 41.3S 174.8E passes late on the UTC date before the local date
    windows = estimate_acquisition_windows(
        "SENTINEL_2", dt.date(2026, 3, 13), -41.3, 174.8
    )
    assert len(windows) == 1
    s, e = windows[0]
    assert s.date() == e.date() == dt.date(2026, 3, 13)
    assert s.hour >= 21


def test_sentinel_not_before():
    datatake = iso("2026-01-24T07:31:09Z")
    windows = estimate_acquisition_windows(
        "SENTINEL_2", dt.date(2026, 1, 24), 15.0, 45.0, not_before=datatake
    )
    assert windows and all(s >= datatake and e > s for s, e in windows)


def test_sentinel_tile_after_midnight_follows_datatake():
    # datatake starts 23:50 on the 13th, and a tile near 157E is sensed after midnight
    datatake = iso("2026-03-13T23:50:00Z")
    windows = estimate_acquisition_windows(
        "SENTINEL_2", dt.date(2026, 3, 13), 0.0, 157.0, not_before=datatake
    )
    assert covers(windows, iso("2026-03-14T00:05:00Z"))
    assert all(s >= datatake for s, _ in windows)
    assert iso("2026-03-14T06:00Z") in gdas_cycles_for_windows(windows)


@pytest.mark.parametrize(
    ("start", "end", "hours"),
    [
        ("2026-03-14T13:00Z", "2026-03-14T14:00Z", [12, 18]),
        ("2026-03-14T11:40Z", "2026-03-14T12:40Z", [6, 12, 18]),
        ("2026-03-14T01:00Z", "2026-03-14T20:00Z", [0, 6, 12, 18, 24]),
    ],
)
def test_gdas_cycles_for_windows(start, end, hours):
    day = iso("2026-03-14T00:00Z")
    assert gdas_cycles_for_windows([(iso(start), iso(end))]) == [
        day + dt.timedelta(hours=h) for h in hours
    ]


def test_unknown_platform():
    with pytest.raises(ValueError, match="LANDSAT_8"):
        estimate_acquisition_time("LANDSAT_7", dt.date(2026, 3, 14), 0.0, 0.0)
